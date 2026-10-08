"""Testes de cabeçalhos de segurança HTTP na resposta da raiz.

Nível: mistura app/PLATAFORMA. Em *.streamlit.app grande parte dos cabeçalhos
é definida pela Streamlit; os testes documentam o estado atual.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.live


def test_x_content_type_options_nosniff(root_response):
    val = (root_response.headers.get("X-Content-Type-Options") or "").lower()
    assert val == "nosniff", "Ausência de X-Content-Type-Options: nosniff."


def test_frame_protection(root_response):
    """Proteção contra clickjacking via X-Frame-Options ou CSP frame-ancestors."""
    xfo = (root_response.headers.get("X-Frame-Options") or "").upper()
    csp = (root_response.headers.get("Content-Security-Policy") or "").lower()
    has_xfo = xfo in ("DENY", "SAMEORIGIN")
    has_csp_fa = "frame-ancestors" in csp
    assert has_xfo or has_csp_fa, (
        "Sem proteção anti-clickjacking (X-Frame-Options ou CSP frame-ancestors)."
    )


def test_referrer_policy(root_response):
    assert root_response.headers.get("Referrer-Policy"), (
        "Sem cabeçalho Referrer-Policy."
    )


def test_content_security_policy_present(root_response):
    assert root_response.headers.get("Content-Security-Policy"), (
        "[plataforma] Sem Content-Security-Policy — reduz mitigação de XSS."
    )


def test_permissions_policy(root_response):
    assert root_response.headers.get("Permissions-Policy"), (
        "Sem Permissions-Policy (restrição de câmera/microfone/geolocalização)."
    )


def test_no_server_version_disclosure(root_response):
    """O cabeçalho Server não deve expor versão detalhada do software."""
    server = root_response.headers.get("Server", "")
    assert not any(ch.isdigit() for ch in server), (
        f"Cabeçalho Server expõe versão: {server!r}"
    )


def test_no_powered_by_disclosure(root_response):
    assert "X-Powered-By" not in root_response.headers, (
        f"X-Powered-By expõe stack: {root_response.headers.get('X-Powered-By')!r}"
    )
