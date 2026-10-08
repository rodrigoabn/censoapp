"""Configuração compartilhada dos testes dinâmicos de segurança.

Alvo padrão: aplicação em produção no Streamlit Community Cloud.
Sobrescreva com a variável de ambiente SECURITY_TARGET.

Os testes só executam quando SECURITY_LIVE=1 (evita bater na produção
acidentalmente). São NÃO INTRUSIVOS: poucas requisições, sem fuzzing e sem
brute-force. Não tocam o Educacenso (terceiro).

Muitos cabeçalhos em *.streamlit.app são controlados pela PLATAFORMA
(Streamlit Cloud), não pela aplicação. Onde aplicável, os testes rotulam o
achado como nível "app" ou "plataforma".
"""

from __future__ import annotations

import os

import pytest
import requests

DEFAULT_TARGET = "https://censoescolar.streamlit.app/"

TIMEOUT = 15
USER_AGENT = "censo-security-scan/1.0 (+defensivo; owner-authorized)"


def target_url() -> str:
    return os.environ.get("SECURITY_TARGET", DEFAULT_TARGET).rstrip("/") + "/"


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
    """Pula toda a suíte se SECURITY_LIVE!=1 ou se o alvo estiver inacessível."""
    if not _live_enabled():
        skip = pytest.mark.skip(reason="Defina SECURITY_LIVE=1 para rodar contra produção.")
        for item in items:
            item.add_marker(skip)
        return

    try:
        requests.get(target_url(), timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
    except requests.RequestException as exc:  # alvo inacessível
        skip = pytest.mark.skip(reason=f"Alvo inacessível: {exc}")
        for item in items:
            item.add_marker(skip)
