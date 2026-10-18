"""Boot do HUB via AppTest.

Sem `.streamlit/secrets.toml`, o modo de autenticação é "aberto": o portão não
bloqueia e a página inicial renderiza sem exceção. É a garantia de que a
integração do gate (chamada única no topo do app.py) não quebrou o fluxo local.
"""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

_RAIZ = Path(__file__).resolve().parents[1]


def test_hub_sobe_sem_excecao(monkeypatch):
    monkeypatch.chdir(_RAIZ)  # app.py usa caminhos relativos (imagem/image.png)
    at = AppTest.from_file(str(_RAIZ / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception
