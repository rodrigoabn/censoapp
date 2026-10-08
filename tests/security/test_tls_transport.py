"""Testes de transporte seguro (TLS/HTTPS) e HSTS.

Nível: majoritariamente PLATAFORMA (Streamlit Cloud termina o TLS).
"""

from __future__ import annotations

from urllib.parse import urlparse

import pytest
import requests

from conftest import TIMEOUT, USER_AGENT, target_url

pytestmark = pytest.mark.live


def test_target_is_https(base_url):
    assert urlparse(base_url).scheme == "https", "O alvo deve usar HTTPS."


def test_certificate_is_valid(session, base_url):
    """Certificado TLS válido (verify=True — falha em cert inválido/expirado)."""
    resp = session.get(base_url, timeout=TIMEOUT, verify=True)
    assert resp.status_code < 500


def test_http_redirects_to_https(base_url):
    """Acesso via HTTP deve redirecionar para HTTPS (não servir em texto claro)."""
    http_url = target_url().replace("https://", "http://", 1)
    try:
        resp = requests.get(
            http_url, timeout=TIMEOUT, allow_redirects=False,
            headers={"User-Agent": USER_AGENT},
        )
    except requests.RequestException:
        pytest.skip("Porta HTTP não acessível (aceitável: apenas HTTPS exposto).")
        return

    if resp.is_redirect or resp.status_code in (301, 302, 307, 308):
        location = resp.headers.get("Location", "")
        assert location.startswith("https://"), f"Redirect não força HTTPS: {location}"
    else:
        # Se não redirecionou, ao menos não pode servir 200 em HTTP claro.
        assert resp.status_code >= 300, "HTTP servindo conteúdo sem redirect para HTTPS."


def test_hsts_header_present(root_response):
    """Strict-Transport-Security recomendado (nível plataforma)."""
    hsts = root_response.headers.get("Strict-Transport-Security")
    assert hsts, (
        "[plataforma] Sem cabeçalho Strict-Transport-Security. "
        "Em *.streamlit.app isso é responsabilidade da Streamlit."
    )
