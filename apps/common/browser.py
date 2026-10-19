"""Helpers de página do Playwright compartilhados pelos coletores (Fase 4.3).

Mover 1:1 de rel/rec (cópias idênticas). `raise_if_expired` ficou em
`apps.common.session` (não aqui) para não criar import circular: `session`
importa `browser`, o contrário não vale.
"""

from __future__ import annotations

from playwright.sync_api import Page


def safe_cleanup(context, page) -> None:
    """Fecha página/contexto com segurança (ignora erros e valores None)."""
    try:
        if context is not None:
            context.clear_cookies()
    except Exception:
        pass
    try:
        if page is not None:
            page.close()
    except Exception:
        pass
    try:
        if context is not None:
            context.close()
    except Exception:
        pass


def wait_loader(page: Page, timeout: int = 6000) -> None:
    """Aguarda o overlay de carregamento (ngx-ui-loader) desaparecer."""
    try:
        page.wait_for_selector("ngx-ui-loader .ngx-overlay", state="hidden", timeout=timeout)
    except Exception:
        pass


def session_expirada(page: Page) -> bool:
    """Detecta se a sessão Keycloak expirou (página de login voltou)."""
    try:
        return page.locator("input#username").is_visible()
    except Exception:
        return False
