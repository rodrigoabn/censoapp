"""Testes de flags de segurança em cookies de sessão.

Nível: PLATAFORMA (cookies emitidos pela Streamlit/infra).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.live


def _iter_set_cookie(resp):
    """Retorna a lista de cabeçalhos Set-Cookie (cru), suportando múltiplos."""
    raw = resp.raw.headers if hasattr(resp, "raw") and resp.raw else None
    if raw is not None and hasattr(raw, "get_all"):
        got = raw.get_all("Set-Cookie")
        if got:
            return got
    sc = resp.headers.get("Set-Cookie")
    return [sc] if sc else []


def test_cookies_present_or_skip(root_response):
    cookies = _iter_set_cookie(root_response)
    if not cookies:
        pytest.skip("Nenhum cookie definido na raiz (sessão via WebSocket).")
    assert cookies


def test_cookies_secure_flag(root_response):
    cookies = _iter_set_cookie(root_response)
    if not cookies:
        pytest.skip("Sem cookies para avaliar.")
    for c in cookies:
        assert "secure" in c.lower(), f"[plataforma] Cookie sem flag Secure: {c}"


def test_cookies_httponly_flag(root_response):
    cookies = _iter_set_cookie(root_response)
    if not cookies:
        pytest.skip("Sem cookies para avaliar.")
    for c in cookies:
        assert "httponly" in c.lower(), f"[plataforma] Cookie sem flag HttpOnly: {c}"


def test_cookies_samesite_flag(root_response):
    cookies = _iter_set_cookie(root_response)
    if not cookies:
        pytest.skip("Sem cookies para avaliar.")
    for c in cookies:
        assert "samesite" in c.lower(), f"[plataforma] Cookie sem atributo SameSite: {c}"
