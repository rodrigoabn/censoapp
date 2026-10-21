"""Testes do módulo comum de sessão (`apps/common/session.py`) — Fase 4.3."""

from __future__ import annotations

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from apps.common import browser, session

# ──────────────────────────── login_and_read ───────────────────────────


class _LocatorLoginFalso:
    def __init__(self, pagina, seletor):
        self._pagina = pagina
        self._seletor = seletor

    def click(self, **k):
        self._pagina.chamadas.append(("click", self._seletor))

    def fill(self, valor):
        self._pagina.chamadas.append(("fill", self._seletor, valor))

    def press(self, tecla):
        self._pagina.chamadas.append(("press", self._seletor, tecla))

    def is_visible(self):
        return self._pagina.form_visivel


class _PaginaLoginFalsa:
    def __init__(self, *, form_visivel=False, botao_timeout=False):
        self.form_visivel = form_visivel
        self.botao_timeout = botao_timeout
        self.chamadas: list[tuple] = []

    def goto(self, url, **k):
        self.chamadas.append(("goto", url))

    def wait_for_selector(self, seletor, state=None, timeout=None):
        self.chamadas.append(("wait_for_selector", seletor, state, timeout))
        if seletor == "#kc-login:not([disabled])" and self.botao_timeout:
            raise PlaywrightTimeoutError("timeout")

    def wait_for_timeout(self, ms):
        self.chamadas.append(("wait_for_timeout", ms))

    def locator(self, seletor):
        self.chamadas.append(("locator", seletor))
        return _LocatorLoginFalso(self, seletor)


def test_login_and_read_caminho_feliz_preenche_e_clica():
    pagina = _PaginaLoginFalsa()

    session.login_and_read(pagina, "123", "senha")  # não levanta

    assert ("goto", "https://educacenso.inep.gov.br/escola/pesquisar") in pagina.chamadas
    assert ("fill", "input#username", "123") in pagina.chamadas
    assert ("fill", "input#password", "senha") in pagina.chamadas
    assert ("click", "#kc-login") in pagina.chamadas
    assert ("wait_for_timeout", 4000) in pagina.chamadas


def test_login_and_read_usa_enter_como_fallback_do_botao():
    pagina = _PaginaLoginFalsa(botao_timeout=True)

    session.login_and_read(pagina, "123", "senha")

    assert ("press", "input#password", "Enter") in pagina.chamadas
    assert ("click", "#kc-login") not in pagina.chamadas


def test_login_and_read_levanta_login_falhou_se_formulario_persiste():
    pagina = _PaginaLoginFalsa(form_visivel=True)

    with pytest.raises(session.LoginFalhou):
        session.login_and_read(pagina, "123", "senha")


# ──────────────────────────── raise_if_expired ─────────────────────────


def test_raise_if_expired_levanta_quando_expirada(monkeypatch):
    monkeypatch.setattr(session, "session_expirada", lambda page: True)

    with pytest.raises(session.SessaoExpirada):
        session.raise_if_expired(object())


def test_raise_if_expired_nao_levanta_quando_sessao_ok(monkeypatch):
    monkeypatch.setattr(session, "session_expirada", lambda page: False)

    session.raise_if_expired(object())


# ───────────────────────── accept_sigilo_if_present ────────────────────


class _LocatorSigiloFalso:
    def __init__(self, pagina, seletor):
        self._pagina = pagina
        self._seletor = seletor

    @property
    def first(self):
        return self

    def count(self):
        return 1

    def is_disabled(self):
        return False

    def is_enabled(self):
        return True

    def check(self, force=False):
        self._pagina.chamadas.append(("check", self._seletor, force))

    def click(self):
        self._pagina.chamadas.append(("click", self._seletor))


class _PaginaSigiloFalsa:
    def __init__(self, *, presente):
        self.presente = presente
        self.chamadas: list[tuple] = []

    def wait_for_selector(self, seletor, state=None, timeout=None):
        self.chamadas.append(("wait_for_selector", seletor, state, timeout))
        if state == "detached":
            return None
        if not self.presente:
            raise PlaywrightTimeoutError("sem diálogo")
        return object()

    def evaluate(self, script):
        self.chamadas.append(("evaluate", script))

    def wait_for_timeout(self, ms):
        self.chamadas.append(("wait_for_timeout", ms))

    def locator(self, seletor):
        self.chamadas.append(("locator", seletor))
        return _LocatorSigiloFalso(self, seletor)


def test_accept_sigilo_ausente_faz_so_a_sonda_curta():
    pagina = _PaginaSigiloFalsa(presente=False)

    session.accept_sigilo_if_present(pagina)

    assert ("wait_for_selector", "mat-dialog-container", None, 1500) in pagina.chamadas
    assert not [c for c in pagina.chamadas if c[0] in ("check", "click")]


def test_accept_sigilo_presente_marca_aceite_e_espera_saida():
    pagina = _PaginaSigiloFalsa(presente=True)

    session.accept_sigilo_if_present(pagina)

    assert ("check", "mat-dialog-container input[type='checkbox']", True) in pagina.chamadas
    assert ("click", "button:has-text('Continuar')") in pagina.chamadas
    assert ("wait_for_selector", "mat-dialog-container", "detached", 5000) in pagina.chamadas


# ─────────────────────────────── select_school ─────────────────────────


class _LocatorSelectFalso:
    def __init__(self, pagina, seletor):
        self._pagina = pagina
        self._seletor = seletor

    @property
    def first(self):
        return self

    def count(self):
        if self._seletor.startswith("a.cursor-pointer"):
            return 1 if self._pagina.link_aparece else 0
        return 0

    def click(self, **k):
        self._pagina.chamadas.append(("click", self._seletor))


class _PaginaSelectFalsa:
    def __init__(self, *, link_aparece=False):
        self.link_aparece = link_aparece
        self.chamadas: list[tuple] = []

    def goto(self, url, **k):
        self.chamadas.append(("goto", url))

    def wait_for_selector(self, seletor, state=None, timeout=None):
        self.chamadas.append(("wait_for_selector", seletor, state, timeout))
        if seletor == "mat-dialog-container":
            # Sonda do termo de sigilo: diálogo nunca presente.
            raise PlaywrightTimeoutError("sem diálogo")

    def wait_for_timeout(self, ms):
        self.chamadas.append(("wait_for_timeout", ms))

    def locator(self, seletor):
        self.chamadas.append(("locator", seletor))
        return _LocatorSelectFalso(self, seletor)

    def fill(self, seletor, valor):
        self.chamadas.append(("fill", seletor, valor))


def test_select_school_portao_por_seletor_uniao_e_falha_sem_link():
    pagina = _PaginaSelectFalsa(link_aparece=False)

    assert session.select_school(pagina, "111") is False
    assert (
        "wait_for_selector",
        "input#username, input[formcontrolname='codigoEscola']",
        None,
        15000,
    ) in pagina.chamadas
    assert ("fill", "input[formcontrolname='codigoEscola']", "111") in pagina.chamadas


def test_select_school_sucesso_usa_after_select():
    pagina = _PaginaSelectFalsa(link_aparece=True)
    vistos: list[object] = []

    def _after_select(page):
        vistos.append(page)

    assert session.select_school(pagina, "111", after_select=_after_select) is True
    assert vistos == [pagina]
    # O clique no link aconteceu antes do hook.
    assert ("click", "a.cursor-pointer:has-text('111')") in pagina.chamadas


def test_select_school_sem_hook_espera_o_botao_gerar():
    pagina = _PaginaSelectFalsa(link_aparece=True)

    assert session.select_school(pagina, "111") is True
    assert (
        "wait_for_selector",
        "mat-dialog-container, button:has-text('Gerar')",
        None,
        10000,
    ) in pagina.chamadas


class _LocatorInvisivel:
    def is_visible(self):
        return False


class _PaginaSemCampo:
    """Página em que o campo `codigoEscola` nunca renderiza (timeout de 30 s)."""

    def __init__(self):
        self.gotos = 0

    def goto(self, url, **k):
        self.gotos += 1

    def wait_for_selector(self, seletor, state=None, timeout=None):
        if seletor == "input[formcontrolname='codigoEscola']":
            raise PlaywrightTimeoutError("campo não apareceu")
        return _LocatorInvisivel()

    def wait_for_timeout(self, ms):
        return None

    def locator(self, seletor):
        return _LocatorInvisivel()


def test_select_school_tenta_tres_vezes_por_padrao():
    """As 4 telas de coleta continuam com o retry interno de navegação."""
    pagina = _PaginaSemCampo()

    with pytest.raises(PlaywrightTimeoutError):
        session.select_school(pagina, "111")

    assert pagina.gotos == 3


def test_select_school_uma_tentativa_quando_o_contexto_da_rodada_pede():
    """Na rodada o retry é por escola: a navegação tenta uma vez só."""
    pagina = _PaginaSemCampo()
    token = session.TENTATIVAS_NAVEGACAO.set(1)
    try:
        with pytest.raises(PlaywrightTimeoutError):
            session.select_school(pagina, "111")
    finally:
        session.TENTATIVAS_NAVEGACAO.reset(token)

    assert pagina.gotos == 1


# ─────────────────────────── marcar_nao_processadas ────────────────────


def test_motivo_interrompido_exato():
    assert session.MOTIVO_INTERROMPIDO == "Coleta interrompida (não processada)"


def test_marcar_nao_processadas_dita_os_registros():
    failures: list[dict] = [{"ja": "existente"}]
    restantes = [
        {"codigo_inep": "111", "nome_unidade": "Escola Um"},
        {"codigo_inep": "222"},  # sem nome → ""
    ]

    session.marcar_nao_processadas(failures, restantes)

    assert failures == [
        {"ja": "existente"},
        {
            "codigo_inep": "111",
            "nome_unidade": "Escola Um",
            "motivo": "Coleta interrompida (não processada)",
        },
        {"codigo_inep": "222", "nome_unidade": "", "motivo": "Coleta interrompida (não processada)"},
    ]


# ─────────── integridade dos aliases nos scrapers (piloto) ────────────


def test_aliases_dos_scrapers_apontam_para_os_modulos_comuns():
    from apps.coleta_recibos_fechamento.src import receipt_scraper
    from apps.coleta_relatorios.src import report_scraper

    for modulo in (report_scraper, receipt_scraper):
        assert modulo.LoginFalhou is session.LoginFalhou
        assert modulo.SessaoExpirada is session.SessaoExpirada
        assert modulo._safe_cleanup is browser.safe_cleanup
        assert modulo._wait_loader is browser.wait_loader
        assert modulo._session_expirada is browser.session_expirada
        assert modulo._login_and_read is session.login_and_read
        assert modulo._accept_sigilo_if_present is session.accept_sigilo_if_present
        assert modulo._select_school is session.select_school
        assert modulo._marcar_nao_processadas is session.marcar_nao_processadas
        assert modulo._MOTIVO_INTERROMPIDO == session.MOTIVO_INTERROMPIDO


def test_raise_if_expired_do_scraper_le_o_monkeypatch_do_modulo(monkeypatch):
    from apps.coleta_recibos_fechamento.src import receipt_scraper
    from apps.coleta_relatorios.src import report_scraper

    for modulo in (report_scraper, receipt_scraper):
        monkeypatch.setattr(modulo, "_session_expirada", lambda page: True)
        with pytest.raises(modulo.SessaoExpirada):
            modulo._raise_if_expired(object())
        monkeypatch.setattr(modulo, "_session_expirada", lambda page: False)
        modulo._raise_if_expired(object())  # não levanta
