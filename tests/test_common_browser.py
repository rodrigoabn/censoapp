"""Testes dos helpers de página comuns (`apps/common/browser.py`) — Fase 4.3."""

from __future__ import annotations

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from apps.common import browser


class _PaginaFalsa:
    """Página fake mínima: registra chamadas; opcionalmente visível/em falha."""

    def __init__(self, *, visivel: bool = False, falha: bool = False):
        self.visivel = visivel
        self.falha = falha
        self.chamadas: list[tuple] = []

    def wait_for_selector(self, seletor, state=None, timeout=None):
        self.chamadas.append(("wait_for_selector", seletor, state, timeout))
        if self.falha:
            raise PlaywrightTimeoutError("timeout")

    def locator(self, seletor):
        self.chamadas.append(("locator", seletor))
        return self

    def is_visible(self):
        return self.visivel


# ───────────────────────────── wait_loader ─────────────────────────────


def test_wait_loader_engole_excecao_e_usa_timeout_padrao():
    pagina = _PaginaFalsa(falha=True)

    browser.wait_loader(pagina)  # não levanta

    assert pagina.chamadas == [
        ("wait_for_selector", "ngx-ui-loader .ngx-overlay", "hidden", 6000),
    ]


def test_wait_loader_aceita_timeout_customizado():
    pagina = _PaginaFalsa()

    browser.wait_loader(pagina, 15000)

    assert pagina.chamadas == [
        ("wait_for_selector", "ngx-ui-loader .ngx-overlay", "hidden", 15000),
    ]


# ─────────────────────────── session_expirada ──────────────────────────


def test_session_expirada_verdadeiro_quando_login_visivel():
    pagina = _PaginaFalsa(visivel=True)

    assert browser.session_expirada(pagina) is True
    assert ("locator", "input#username") in pagina.chamadas


def test_session_expirada_falso_quando_login_invisivel():
    assert browser.session_expirada(_PaginaFalsa(visivel=False)) is False


def test_session_expirada_falso_quando_locator_levanta():
    class _PaginaQuebrada:
        def locator(self, seletor):
            raise RuntimeError("boom")

    assert browser.session_expirada(_PaginaQuebrada()) is False


# ───────────────────────────── safe_cleanup ────────────────────────────


def test_safe_cleanup_aceita_none_sem_erro():
    browser.safe_cleanup(None, None)  # não levanta


def test_safe_cleanup_ordem_clear_cookies_pagina_contexto():
    chamadas: list[str] = []

    class _Contexto:
        def clear_cookies(self):
            chamadas.append("clear_cookies")

        def close(self):
            chamadas.append("context.close")

    class _Pagina:
        def close(self):
            chamadas.append("page.close")

    browser.safe_cleanup(_Contexto(), _Pagina())

    assert chamadas == ["clear_cookies", "page.close", "context.close"]


def test_safe_cleanup_continua_apos_erros():
    chamadas: list[str] = []

    class _Contexto:
        def clear_cookies(self):
            raise RuntimeError("boom")

        def close(self):
            chamadas.append("context.close")

    class _Pagina:
        def close(self):
            chamadas.append("page.close")

    browser.safe_cleanup(_Contexto(), _Pagina())

    assert chamadas == ["page.close", "context.close"]
