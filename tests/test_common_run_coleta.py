"""Testes do motor genérico de coleta (`apps/common/coleta.py`) — Fase 4.4.

Contrato: o laço canônico do Cadastros generalizado — login 2× (sleep(1)
entre tentativas), stop_check antes/depois do scrape, `scrape_one → None` =
escola não encontrada, retry pós-`SessaoExpirada` (na verificação de sessão e
na ficha), motivos formatados, callback de gravação antes do append e pausa
por escola. Tudo com hooks gravadores (DI), sem rede.
"""

from __future__ import annotations

import logging

import pytest

from apps.common import browser as _browser
from apps.common import coleta, session

ESCOLAS = [
    {"codigo_inep": "111", "nome_unidade": "Escola Um"},
    {"codigo_inep": "222", "nome_unidade": "Escola Dois"},
]


class _PaginaFalsa:
    def __init__(self):
        self.fechada = False

    def close(self):
        self.fechada = True


class _ContextoFalso:
    def __init__(self):
        self.pagina = _PaginaFalsa()
        self.limpo = False
        self.fechado = False

    def new_page(self):
        return self.pagina

    def clear_cookies(self):
        self.limpo = True

    def close(self):
        self.fechado = True


class _BrowserFalso:
    def __init__(self):
        self.kwargs = None
        self.contexto = _ContextoFalso()

    def new_context(self, **kwargs):
        self.kwargs = kwargs
        return self.contexto


class _Progresso:
    def __init__(self):
        self.eventos = []

    def __call__(self, i, total, codigo, nome, estado):
        self.eventos.append((i, total, codigo, nome, estado))


@pytest.fixture(autouse=True)
def _sem_espera(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)


def _hooks(**over):
    base = dict(
        login_and_read=lambda page, login, senha: None,
        session_expirada=lambda page: False,
        safe_cleanup=_browser.safe_cleanup,
        pausa_entre_escolas=coleta.pausa_entre_escolas,
        log_tempo_escola=lambda codigo, t0: None,
        registrar_sucesso=coleta.registrar_sucesso,
        marcar_nao_processadas=session.marcar_nao_processadas,
    )
    base.update(over)
    return coleta.ColetaHooks(**base)


def _textos(**over):
    base = dict(
        log_abort="Falha no login inicial. Abortando coleta.",
        log_inicio_loop="Login realizado com sucesso. Iniciando loop de escolas.",
        formatar_log_erro=lambda codigo, exc: f"[{codigo}] Erro durante coleta: {exc}",
        formatar_motivo_relogin=lambda exc: str(exc),
    )
    base.update(over)
    return coleta.TextosColeta(**base)


def _rodar(browser, escolas, scrape_one, hooks, textos=None, **kw):
    return coleta.run_coleta(
        browser,
        "l",
        "s",
        escolas,
        scrape_one=scrape_one,
        hooks=hooks,
        textos=textos or _textos(),
        logger=logging.getLogger("teste_coleta"),
        accept_downloads=True,
        **kw,
    )


def _nunca(context, page, codigo, nome):
    raise AssertionError("scrape_one não deveria ser chamado")


# ── login inicial ──────────────────────────────────────────────────────────


def test_falha_de_login_marca_todas_e_faz_cleanup(caplog):
    browser = _BrowserFalso()
    tentativas = []

    def login_and_read(page, login, senha):
        tentativas.append(1)
        raise coleta.LoginFalhou()

    with caplog.at_level(logging.ERROR):
        outputs, failures = _rodar(browser, ESCOLAS, _nunca, _hooks(login_and_read=login_and_read))

    assert outputs == []
    assert failures == [
        {"codigo_inep": "111", "nome_unidade": "Escola Um", "motivo": "Falha no login"},
        {"codigo_inep": "222", "nome_unidade": "Escola Dois", "motivo": "Falha no login"},
    ]
    assert len(tentativas) == 2
    assert browser.contexto.limpo is True
    assert browser.contexto.fechado is True
    assert browser.contexto.pagina.fechada is True
    assert "Falha no login inicial. Abortando coleta." in caplog.text


def test_retry_de_login_apos_uma_falha(caplog):
    browser = _BrowserFalso()
    tentativas = []

    def login_and_read(page, login, senha):
        tentativas.append(1)
        if len(tentativas) == 1:
            raise coleta.LoginFalhou()

    with caplog.at_level(logging.INFO):
        outputs, failures = _rodar(
            browser,
            ESCOLAS[:1],
            lambda context, page, codigo, nome: b"csv",
            _hooks(login_and_read=login_and_read),
        )

    assert len(tentativas) == 2
    assert outputs == [(ESCOLAS[0], b"csv")]
    assert failures == []
    assert "Login realizado com sucesso. Iniciando loop de escolas." in caplog.text


# ── stop_check ─────────────────────────────────────────────────────────────


def test_stop_antes_da_escola_marca_as_restantes():
    browser = _BrowserFalso()
    outputs, failures = _rodar(browser, ESCOLAS, _nunca, _hooks(), stop_check=lambda: True)

    assert outputs == []
    assert failures == [
        {
            "codigo_inep": "111",
            "nome_unidade": "Escola Um",
            "motivo": "Coleta interrompida (não processada)",
        },
        {
            "codigo_inep": "222",
            "nome_unidade": "Escola Dois",
            "motivo": "Coleta interrompida (não processada)",
        },
    ]


def test_stop_apos_scrape_descarta_atual_e_marca_restante():
    browser = _BrowserFalso()
    chamadas = {"n": 0}

    def stop_check():
        chamadas["n"] += 1
        return chamadas["n"] > 3

    scrapes = []

    def scrape_one(context, page, codigo, nome):
        scrapes.append(codigo)
        return b"dados"

    progresso = _Progresso()
    outputs, failures = _rodar(
        browser, ESCOLAS, scrape_one, _hooks(), stop_check=stop_check, on_progress=progresso
    )

    assert [e["codigo_inep"] for e, _ in outputs] == ["111"]
    assert failures == [
        {
            "codigo_inep": "222",
            "nome_unidade": "Escola Dois",
            "motivo": "Coleta interrompida (não processada)",
        }
    ]
    assert scrapes == ["111", "222"]  # o dado da 222 foi descartado
    assert progresso.eventos[-1] == (2, 2, "222", "Escola Dois", "interrompido")


# ── escola não encontrada e sucesso ────────────────────────────────────────


def test_scrape_none_vira_escola_nao_encontrada(caplog):
    browser = _BrowserFalso()
    progresso = _Progresso()

    def scrape_one(context, page, codigo, nome):
        return None if codigo == "111" else b"ok"

    with caplog.at_level(logging.WARNING):
        outputs, failures = _rodar(
            browser,
            ESCOLAS,
            scrape_one,
            _hooks(),
            textos=_textos(
                formatar_log_nao_encontrada=lambda codigo: f"[{codigo}] Escola não encontrada."
            ),
            on_progress=progresso,
        )

    assert [e["codigo_inep"] for e, _ in outputs] == ["222"]
    assert failures == [
        {"codigo_inep": "111", "nome_unidade": "Escola Um", "motivo": "Escola não encontrada"}
    ]
    assert "[111] Escola não encontrada." in caplog.text
    assert (1, 2, "111", "Escola Um", "erro: escola não encontrada") in progresso.eventos


def test_registrar_sucesso_chama_callback_antes_do_append():
    outputs = []
    visto = []

    def on_school_done(escola, dados):
        visto.append(list(outputs))

    coleta.registrar_sucesso(outputs, on_school_done, {"codigo_inep": "111"}, b"x")

    assert visto == [[]]
    assert outputs == [({"codigo_inep": "111"}, b"x")]


def test_sucesso_ordem_dos_progressos_e_log_de_tempo(caplog):
    browser = _BrowserFalso()
    tempos = []
    progresso = _Progresso()

    with caplog.at_level(logging.INFO):
        outputs, failures = _rodar(
            browser,
            ESCOLAS[:1],
            lambda context, page, codigo, nome: b"csv",
            _hooks(log_tempo_escola=lambda codigo, t0: tempos.append(codigo)),
            on_progress=progresso,
        )

    assert outputs == [(ESCOLAS[0], b"csv")]
    assert failures == []
    assert [e[4] for e in progresso.eventos] == ["Coletando dados ...", "concluído"]
    assert tempos == ["111"]


# ── sessão expirada na verificação antes da escola ─────────────────────────


def test_sessao_expirada_na_verificacao_reloga_e_continua(caplog):
    browser = _BrowserFalso()
    logins = []
    respostas = iter([True, False])

    def login_and_read(page, login, senha):
        logins.append(1)

    with caplog.at_level(logging.INFO):
        outputs, failures = _rodar(
            browser,
            ESCOLAS[:1],
            lambda context, page, codigo, nome: b"csv",
            _hooks(login_and_read=login_and_read, session_expirada=lambda page: next(respostas)),
        )

    assert len(logins) == 2
    assert outputs == [(ESCOLAS[0], b"csv")]
    assert failures == []
    assert "Sessão expirada. Realizando re-login..." in caplog.text
    assert "Re-login concluído." in caplog.text


def test_sessao_expirada_com_relogin_falho_usa_motivo_formatado():
    browser = _BrowserFalso()
    tentativas = {"n": 0}

    def login_and_read(page, login, senha):
        tentativas["n"] += 1
        if tentativas["n"] > 1:
            raise RuntimeError("caiu")

    progresso = _Progresso()
    tempos = []
    outputs, failures = _rodar(
        browser,
        ESCOLAS[:1],
        _nunca,
        _hooks(
            login_and_read=login_and_read,
            session_expirada=lambda page: True,
            log_tempo_escola=lambda codigo, t0: tempos.append(codigo),
        ),
        textos=_textos(formatar_motivo_relogin=lambda exc: f"X::{exc}"),
        on_progress=progresso,
    )

    assert outputs == []
    assert failures == [
        {"codigo_inep": "111", "nome_unidade": "Escola Um", "motivo": "Erro (re-login): X::caiu"}
    ]
    assert tempos == ["111"]
    assert progresso.eventos[1] == (1, 1, "111", "Escola Um", "erro: sessão expirada — caiu")


# ── SessaoExpirada durante o scrape (ficha) ────────────────────────────────


def test_scrape_com_sessao_expirada_repete_apos_relogin(caplog):
    browser = _BrowserFalso()
    logins = []
    chamadas = {"n": 0}

    def login_and_read(page, login, senha):
        logins.append(1)

    def scrape_one(context, page, codigo, nome):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise coleta.SessaoExpirada()
        return b"csv"

    with caplog.at_level(logging.WARNING):
        outputs, failures = _rodar(
            browser, ESCOLAS[:1], scrape_one, _hooks(login_and_read=login_and_read)
        )

    assert len(logins) == 2  # login inicial + re-login da ficha
    assert chamadas["n"] == 2
    assert outputs == [(ESCOLAS[0], b"csv")]
    assert failures == []
    assert "Sessão expirada ao abrir a ficha. Re-logando e repetindo..." in caplog.text


def test_scrape_com_sessao_expirada_e_relogin_falho(caplog):
    browser = _BrowserFalso()
    tentativas = {"n": 0}

    def login_and_read(page, login, senha):
        tentativas["n"] += 1
        if tentativas["n"] > 1:
            raise RuntimeError("morreu")

    def scrape_one(context, page, codigo, nome):
        raise coleta.SessaoExpirada()

    with caplog.at_level(logging.ERROR):
        outputs, failures = _rodar(
            browser, ESCOLAS[:1], scrape_one, _hooks(login_and_read=login_and_read)
        )

    assert outputs == []
    assert failures == [
        {"codigo_inep": "111", "nome_unidade": "Escola Um", "motivo": "Erro (re-login): morreu"}
    ]
    assert "Falha no re-login: morreu" in caplog.text


def test_scrape_com_sessao_expirada_e_falha_apos_relogin(caplog):
    browser = _BrowserFalso()
    chamadas = {"n": 0}

    def scrape_one(context, page, codigo, nome):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise coleta.SessaoExpirada()
        raise RuntimeError("boom")

    progresso = _Progresso()
    with caplog.at_level(logging.ERROR):
        outputs, failures = _rodar(
            browser, ESCOLAS[:1], scrape_one, _hooks(), on_progress=progresso
        )

    assert outputs == []
    assert failures == [
        {"codigo_inep": "111", "nome_unidade": "Escola Um", "motivo": "Erro (após re-login): boom"}
    ]
    assert "Falha após re-login: boom" in caplog.text
    assert progresso.eventos[-1] == (1, 1, "111", "Escola Um", "erro: boom")


def test_scrape_none_apos_relogin_usa_log_especifico(caplog):
    browser = _BrowserFalso()
    chamadas = {"n": 0}

    def scrape_one(context, page, codigo, nome):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise coleta.SessaoExpirada()
        return None

    with caplog.at_level(logging.WARNING):
        outputs, failures = _rodar(
            browser,
            ESCOLAS[:1],
            scrape_one,
            _hooks(),
            textos=_textos(
                formatar_log_nao_encontrada_pos_relogin=lambda codigo: (
                    f"[{codigo}] Escola não encontrada após re-login."
                )
            ),
        )

    assert outputs == []
    assert failures == [
        {"codigo_inep": "111", "nome_unidade": "Escola Um", "motivo": "Escola não encontrada"}
    ]
    assert "[111] Escola não encontrada após re-login." in caplog.text


# ── exceção genérica, contexto e pausa ─────────────────────────────────────


def test_excecao_generica_vira_erro_com_motivo(caplog):
    browser = _BrowserFalso()
    progresso = _Progresso()

    def scrape_one(context, page, codigo, nome):
        raise RuntimeError("boom")

    with caplog.at_level(logging.ERROR):
        outputs, failures = _rodar(browser, ESCOLAS[:1], scrape_one, _hooks(), on_progress=progresso)

    assert outputs == []
    assert failures == [
        {"codigo_inep": "111", "nome_unidade": "Escola Um", "motivo": "Erro: boom"}
    ]
    assert "[111] Erro durante coleta: boom" in caplog.text
    assert progresso.eventos[-1] == (1, 1, "111", "Escola Um", "erro: boom")


def test_accept_downloads_repassado_ao_contexto():
    browser = _BrowserFalso()
    _rodar(browser, [], _nunca, _hooks())
    assert browser.kwargs == {"accept_downloads": True}

    browser2 = _BrowserFalso()
    coleta.run_coleta(
        browser2,
        "l",
        "s",
        [],
        scrape_one=_nunca,
        hooks=_hooks(),
        textos=_textos(),
        logger=logging.getLogger("teste_coleta"),
        accept_downloads=False,
    )
    assert browser2.kwargs == {"accept_downloads": False}


def test_pausa_uma_vez_por_escola_e_cleanup_no_fim():
    browser = _BrowserFalso()
    pausas = []
    outputs, failures = _rodar(
        browser,
        ESCOLAS,
        lambda context, page, codigo, nome: b"x",
        _hooks(pausa_entre_escolas=lambda: pausas.append(1) or 0.0),
    )

    assert len(pausas) == 2
    assert len(outputs) == 2
    assert failures == []
    assert browser.contexto.limpo is True
    assert browser.contexto.fechado is True
