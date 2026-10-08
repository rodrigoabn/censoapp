"""Testes de exposição de informação e caminhos sensíveis.

Verifica que arquivos-fonte/segredos e diretórios de VCS não são servidos e
que a aplicação não vaza detalhes internos em respostas.
"""

from __future__ import annotations

import pytest

from conftest import TIMEOUT

pytestmark = pytest.mark.live

# Caminhos que NUNCA devem retornar 200 com conteúdo sensível.
SENSITIVE_PATHS = [
    ".git/config",
    ".git/HEAD",
    "credenciais.json",
    "apps/coleta_cadastros_escolas/docs/credenciais.json",
    ".streamlit/secrets.toml",
    "app.py",
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
    ".env",
    "docs_temporarios/arquivo%20professor.csv",
]


@pytest.mark.parametrize("path", SENSITIVE_PATHS)
def test_sensitive_paths_not_served(session, base_url, path):
    resp = session.get(base_url + path, timeout=TIMEOUT, allow_redirects=False)
    # Streamlit SPA costuma devolver o index (200) para rotas desconhecidas;
    # o crítico é NÃO servir o conteúdo real do arquivo sensível.
    if resp.status_code == 200:
        body = resp.text[:4096].lower()
        leaked_markers = [
            "private_key", "service_account", "-----begin",
            "aws_secret", "password =", "senha =",
            "import streamlit",  # código-fonte app.py
        ]
        assert not any(m in body for m in leaked_markers), (
            f"Possível vazamento de conteúdo sensível em /{path}"
        )


def test_stcore_health_no_leak(session, base_url):
    """O endpoint de saúde do Streamlit não deve vazar detalhes internos."""
    resp = session.get(base_url + "_stcore/health", timeout=TIMEOUT)
    if resp.status_code == 200:
        body = resp.text.lower()
        for marker in ("traceback", "/home/", "exception", "secret"):
            assert marker not in body, f"Health endpoint vaza informação: {marker!r}"


def test_error_page_not_verbose(session, base_url):
    """Página de erro/404 não deve exibir stack trace ou caminhos do servidor."""
    resp = session.get(base_url + "rota-inexistente-scan-xyz", timeout=TIMEOUT)
    body = resp.text.lower()
    for marker in ("traceback (most recent call last)", 'file "/home/', "line ", "/home/appuser"):
        assert marker not in body, f"Página de erro verbosa expõe: {marker!r}"
