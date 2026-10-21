"""Testes do motor genérico de coleta (`apps/common/coleta.py`) — Fase 4.4.

Contrato: o laço canônico do Cadastros generalizado — login 2× em
instabilidade (mensagem do portal aborta na hora), stop_check antes/depois do
scrape, `scrape_one → None` = escola não encontrada, retry pós-`SessaoExpirada`
(na verificação de sessão e na ficha), motivos formatados, callback de gravação
antes do append e pausa por escola. Tudo com hooks gravadores (DI), sem rede.
"""

from __future__ import annotations

import logging

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

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


def test_falha_de_login_com_mensagem_aborta_e_faz_cleanup(caplog):
    """Senha recusada pelo portal: aborta na hora, loga o motivo e limpa a sessão."""
    browser = _BrowserFalso()
    tentativas = []

    def login_and_read(page, login, senha):
        tentativas.append(1)
        raise coleta.LoginFalhou("Nome de usuário ou senha inválida.")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(coleta.LoginFalhou) as excinfo:
            _rodar(browser, ESCOLAS, _nunca, _hooks(login_and_read=login_and_read))

    assert excinfo.value.mensagem == "Nome de usuário ou senha inválida."
    assert excinfo.value.detalhe == "Nome de usuário ou senha inválida."
    assert len(tentativas) == 1  # recusa do portal não é repetida
    assert browser.contexto.limpo is True
    assert browser.contexto.fechado is True
    assert browser.contexto.pagina.fechada is True
    assert "Falha no login inicial. Abortando coleta." in caplog.text
    assert "Nome de usuário ou senha inválida." in caplog.text


def test_falha_de_login_sem_mensagem_tenta_duas_vezes(caplog):
    """Sem mensagem do portal (instabilidade), o login é repetido uma vez."""
    browser = _BrowserFalso()
    tentativas = []

    def login_and_read(page, login, senha):
        tentativas.append(1)
        raise coleta.LoginFalhou()

    with caplog.at_level(logging.ERROR):
        with pytest.raises(coleta.LoginFalhou) as excinfo:
            _rodar(browser, ESCOLAS, _nunca, _hooks(login_and_read=login_and_read))

    assert len(tentativas) == 2
    assert excinfo.value.mensagem is None
    assert "formulário de login continuou visível" in excinfo.value.detalhe
    assert browser.contexto.fechado is True


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
        {"codigo_inep": "111", "nome_unidade": "Escola Um", "motivo": "Erro (re-login): X::caiu", "timeout": False}
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
        {"codigo_inep": "111", "nome_unidade": "Escola Um", "motivo": "Erro (re-login): morreu", "timeout": False}
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
        {"codigo_inep": "111", "nome_unidade": "Escola Um", "motivo": "Erro (após re-login): boom", "timeout": False}
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
        {"codigo_inep": "111", "nome_unidade": "Escola Um", "motivo": "Erro: boom", "timeout": False}
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


# ── marca de timeout (a rodada da 1ª Etapa usa para repetir a escola) ──────


def test_timeout_marca_a_falha_para_nova_tentativa():
    def scrape_one(context, page, codigo, nome):
        raise PlaywrightTimeoutError("Page.wait_for_selector: Timeout 30000ms exceeded.")

    _outputs, failures = _rodar(_BrowserFalso(), ESCOLAS[:1], scrape_one, _hooks())

    assert failures[0]["motivo"] == "Erro: Page.wait_for_selector: Timeout 30000ms exceeded."
    assert failures[0]["timeout"] is True


def test_erro_comum_nao_e_marcado_como_timeout():
    def scrape_one(context, page, codigo, nome):
        raise ValueError("boom")

    _outputs, failures = _rodar(_BrowserFalso(), ESCOLAS[:1], scrape_one, _hooks())

    assert failures[0]["motivo"] == "Erro: boom"
    assert failures[0]["timeout"] is False


def test_timeout_no_login_aborta_com_o_motivo(caplog):
    def login_and_read(page, login, senha):
        raise PlaywrightTimeoutError("Page.goto: Timeout 30000ms exceeded.")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(coleta.LoginFalhou) as excinfo:
            _rodar(
                _BrowserFalso(), ESCOLAS, _nunca, _hooks(login_and_read=login_and_read)
            )

    assert excinfo.value.mensagem is None
    assert "TimeoutError" in excinfo.value.detalhe
    assert "Page.goto: Timeout 30000ms exceeded." in excinfo.value.detalhe
    assert "Page.goto: Timeout 30000ms exceeded." in caplog.text


# ── nova tentativa por escola (só a rodada automática liga) ────────────────

PRAZO_TIMEOUT = "Page.wait_for_selector: Timeout 30000ms exceeded."


@pytest.fixture
def retry_da_rodada():
    """Liga o retry da rodada (5 tentativas) sem esperar de verdade."""
    tokens = (
        coleta.TENTATIVAS_TIMEOUT.set(coleta.MAX_TENTATIVAS_TIMEOUT),
        coleta.ESPERA_TENTATIVAS.set(0.0),
    )
    yield
    for var, token in zip((coleta.TENTATIVAS_TIMEOUT, coleta.ESPERA_TENTATIVAS), tokens):
        var.reset(token)


def test_sem_a_rodada_timeout_nao_repete_a_escola():
    """Fora da rodada (default 1 tentativa) o comportamento é o de sempre."""
    assert coleta.TENTATIVAS_TIMEOUT.get() == 1
    chamadas = []

    def scrape_one(context, page, codigo, nome):
        chamadas.append(codigo)
        raise PlaywrightTimeoutError(PRAZO_TIMEOUT)

    _outputs, failures = _rodar(_BrowserFalso(), ESCOLAS[:1], scrape_one, _hooks())

    assert chamadas == ["111"]
    assert failures[0]["timeout"] is True


def test_timeout_repete_a_mesma_escola_antes_de_seguir(retry_da_rodada):
    """A fila NÃO avança: a escola com timeout é repetida na hora."""
    chamadas = []
    falhou = {"uma": False}

    def scrape_one(context, page, codigo, nome):
        chamadas.append(codigo)
        if codigo == "111" and not falhou["uma"]:
            falhou["uma"] = True
            raise PlaywrightTimeoutError(PRAZO_TIMEOUT)
        return f"dados-{codigo}"

    progresso = _Progresso()
    outputs, failures = _rodar(
        _BrowserFalso(), ESCOLAS, scrape_one, _hooks(), on_progress=progresso
    )

    assert chamadas == ["111", "111", "222"]
    assert outputs == [(ESCOLAS[0], "dados-111"), (ESCOLAS[1], "dados-222")]
    assert failures == []
    assert (1, 2, "111", "Escola Um", "nova tentativa 2 de 5 (timeout)") in progresso.eventos
    assert [e[4] for e in progresso.eventos if e[2] == "111"] == [
        "Coletando dados ...",
        "nova tentativa 2 de 5 (timeout)",
        "Coletando dados ...",
        "concluído",
    ]


def test_timeout_esgota_as_cinco_tentativas_e_vira_pendencia(retry_da_rodada):
    """1 tentativa original + 4 repetições; depois a fila segue."""
    chamadas = []

    def scrape_one(context, page, codigo, nome):
        chamadas.append(codigo)
        if codigo == "111":
            raise PlaywrightTimeoutError(PRAZO_TIMEOUT)
        return "ok"

    outputs, failures = _rodar(_BrowserFalso(), ESCOLAS, scrape_one, _hooks())

    assert chamadas == ["111"] * 5 + ["222"]
    assert [e["codigo_inep"] for e, _ in outputs] == ["222"]
    assert failures == [
        {
            "codigo_inep": "111",
            "nome_unidade": "Escola Um",
            "motivo": f"Erro: {PRAZO_TIMEOUT}",
            "timeout": True,
        }
    ]


def test_erro_comum_nao_ganha_nova_tentativa(retry_da_rodada):
    chamadas = []

    def scrape_one(context, page, codigo, nome):
        chamadas.append(codigo)
        raise RuntimeError("portal fora do ar")

    _outputs, failures = _rodar(_BrowserFalso(), ESCOLAS, scrape_one, _hooks())

    assert chamadas == ["111", "222"]
    assert failures[0]["timeout"] is False


def test_interrupcao_vence_a_espera_da_nova_tentativa(retry_da_rodada):
    """Interromper durante a espera não dispara outra tentativa."""
    chamadas = []
    interromper = {"flag": False}

    def scrape_one(context, page, codigo, nome):
        chamadas.append(codigo)
        interromper["flag"] = True  # usuário interrompeu durante a coleta
        raise PlaywrightTimeoutError(PRAZO_TIMEOUT)

    outputs, failures = _rodar(
        _BrowserFalso(),
        ESCOLAS,
        scrape_one,
        _hooks(),
        stop_check=lambda: interromper["flag"],
    )

    assert chamadas == ["111"]
    assert outputs == []
    assert failures[0]["codigo_inep"] == "111"
    assert failures[0]["timeout"] is True
    assert failures[1]["motivo"] == "Coleta interrompida (não processada)"


def test_sucesso_na_nova_tentativa_grava_uma_vez_so(retry_da_rodada):
    """A tentativa que errou não deixa dados: só a coleta correta permanece."""
    chamadas = {"n": 0}
    gravadas = []

    def scrape_one(context, page, codigo, nome):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise PlaywrightTimeoutError(PRAZO_TIMEOUT)
        return "unica"

    def on_school_done(escola, dados):
        gravadas.append((escola["codigo_inep"], dados))

    outputs, failures = _rodar(
        _BrowserFalso(),
        ESCOLAS[:1],
        scrape_one,
        _hooks(),
        on_school_done=on_school_done,
    )

    assert chamadas["n"] == 2
    assert gravadas == [("111", "unica")]
    assert outputs == [(ESCOLAS[0], "unica")]
    assert failures == []


def test_espera_interrompivel_dorme_em_fatias(monkeypatch):
    dormidas = []
    monkeypatch.setattr(coleta.time, "sleep", lambda segundos: dormidas.append(segundos))

    assert coleta.esperar_interrompivel(0.6) is False
    assert dormidas == [0.25, 0.25, 0.1]


def test_espera_interrompivel_para_na_hora(monkeypatch):
    dormidas = []
    monkeypatch.setattr(coleta.time, "sleep", lambda segundos: dormidas.append(segundos))

    assert coleta.esperar_interrompivel(5.0, lambda: len(dormidas) >= 2) is True
    assert len(dormidas) == 2


def test_falha_rotineira_mapeada_nao_e_timeout():
    class _Rotineira(Exception):
        pass

    def scrape_one(context, page, codigo, nome):
        raise _Rotineira("sem relatório")

    textos = _textos(mapear_excecao=lambda exc: ("Relatório inexistente", "Relatório inexistente."))
    _outputs, failures = _rodar(_BrowserFalso(), ESCOLAS[:1], scrape_one, _hooks(), textos)

    assert failures[0]["timeout"] is False
