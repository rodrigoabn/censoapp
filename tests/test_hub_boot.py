"""Boot do HUB via AppTest.

O HUB roda na rede local sem autenticação própria: a página inicial deve
renderizar sem exceção e sem depender de secrets ou de tela de entrada.
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
