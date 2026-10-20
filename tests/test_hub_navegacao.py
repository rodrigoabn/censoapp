"""Navegação do HUB via AppTest.

A aplicação roda sem autenticação própria. O teste garante que o HUB abre
direto na página inicial, que o menu lateral troca de página e que a limpeza
executada na troca descarta o estado da página anterior, preservando apenas a
navegação.
"""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

_RAIZ = Path(__file__).resolve().parents[1]
_GRUPO = "Coleta do Educacenso"


def _novo_app(monkeypatch) -> AppTest:
    monkeypatch.chdir(_RAIZ)  # app.py usa caminhos relativos (imagem/image.png)
    return AppTest.from_file(str(_RAIZ / "app.py"), default_timeout=60).run()


def test_hub_abre_sem_tela_de_senha(monkeypatch):
    at = _novo_app(monkeypatch)
    assert not at.exception
    rotulos = [(campo.label or "").lower() for campo in at.text_input]
    assert not any("senha de acesso" in rotulo for rotulo in rotulos)


def test_navegacao_troca_pagina_e_limpa_estado(monkeypatch):
    at = _novo_app(monkeypatch)
    at.session_state["estado_da_pagina_anterior"] = "x"

    at.button(key=f"nav_{_GRUPO}_0").click().run()
    assert at.session_state["nav_page"] == "Dados Cadastrais da Unidades"
    assert "estado_da_pagina_anterior" not in at.session_state

    at.button(key=f"nav_{_GRUPO}_1").click().run()
    assert at.session_state["nav_page"] == "Dados dos Gestores Escolares"
    assert not at.exception
