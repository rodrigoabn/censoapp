"""Configuração compartilhada dos testes dinâmicos de segurança.

Alvo: o HUB na intranet — defina sempre `SECURITY_TARGET` (não há alvo
padrão), por exemplo:

    SECURITY_LIVE=1 SECURITY_TARGET=https://censo.seduct.intra/ \
        uv run python -m pytest tests/security/

Com TLS interno (CA do Caddy), aponte `REQUESTS_CA_BUNDLE` para o certificado
raiz (ver runbook).

Os testes só executam quando SECURITY_LIVE=1 (evita bater na produção
acidentalmente). São NÃO INTRUSIVOS: poucas requisições, sem fuzzing e sem
brute-force. Não tocam o Educacenso (terceiro).

Parte dos cabeçalhos vem do proxy de hospedagem, não da aplicação; onde
aplicável, os testes rotulam o achado como nível "app" ou "plataforma".
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import requests

TIMEOUT = 15
USER_AGENT = "censo-security-scan/1.0 (+defensivo; owner-authorized)"


def target_url() -> str:
    """Alvo dos testes ao vivo (com barra final). Sem padrão: exige explícito."""
    alvo = os.environ.get("SECURITY_TARGET", "").strip()
    if not alvo:
        pytest.skip("Defina SECURITY_TARGET (não há alvo padrão).")
    return alvo.rstrip("/") + "/"


def _live_enabled() -> bool:
    return os.environ.get("SECURITY_LIVE") == "1"


@pytest.fixture(scope="session")
def base_url() -> str:
    return target_url()


@pytest.fixture(scope="session")
def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


@pytest.fixture(scope="session")
def root_response(session: requests.Session, base_url: str) -> requests.Response:
    """GET único da raiz, reutilizado pelos testes (baixo volume de requisições)."""
    return session.get(base_url, timeout=TIMEOUT, allow_redirects=True)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "live: testes que fazem requisições reais à produção"
    )


def pytest_collection_modifyitems(config, items):
    """Pula a suíte se SECURITY_LIVE!=1, se faltar SECURITY_TARGET ou se o alvo
    estiver inacessível."""
    security_root = Path(__file__).parent
    security_items = [
        item for item in items if security_root in Path(item.path).parents
    ]
    if not security_items:
        return

    if not _live_enabled():
        skip = pytest.mark.skip(reason="Defina SECURITY_LIVE=1 para rodar contra o alvo.")
        for item in security_items:
            item.add_marker(skip)
        return

    if not os.environ.get("SECURITY_TARGET", "").strip():
        skip = pytest.mark.skip(reason="Defina SECURITY_TARGET (não há alvo padrão).")
        for item in security_items:
            item.add_marker(skip)
        return

    try:
        requests.get(target_url(), timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
    except requests.RequestException as exc:  # alvo inacessível
        skip = pytest.mark.skip(reason=f"Alvo inacessível: {exc}")
        for item in security_items:
            item.add_marker(skip)
