"""Regressão: navegar no menu do HUB não pode voltar à tela de senha.

Cenário real (modo ``[auth_simples]``): a limpeza de estado executada na troca
de página apagava a marca ``auth_ok`` do ``session_state``; no clique seguinte,
o portão de autenticação pedia a senha de novo. O teste sobe o ``app.py`` real
via ``AppTest``, autentica, navega duas vezes pelo menu e garante que a sessão
sobreviveu à limpeza.
"""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

import auth_gate

_RAIZ = Path(__file__).resolve().parents[1]
_SENHA = "senha-de-teste"
_GRUPO = "Coleta do Educacenso"


def _novo_app(monkeypatch) -> AppTest:
    monkeypatch.chdir(_RAIZ)  # app.py usa caminhos relativos (imagem/image.png)
    monkeypatch.delenv("CENSO_AUTH_MODE", raising=False)
    # Determinístico: não depende do .streamlit/secrets.toml local (não versionado).
    monkeypatch.setattr(
        auth_gate, "_secrets_dict", lambda st: {"auth_simples": {"senha": _SENHA}}
    )
    return AppTest.from_file(str(_RAIZ / "app.py"), default_timeout=60)


def _autenticar(at: AppTest) -> AppTest:
    at.run()  # sem sessão: o portão mostra a tela de senha
    at.text_input[0].set_value(_SENHA)
    at.button(key="auth_entrar").click().run()
    assert "auth_ok" in at.session_state and at.session_state["auth_ok"] is True
    return at


def _tem_tela_de_senha(at: AppTest) -> bool:
    return any("Senha de acesso" in (campo.label or "") for campo in at.text_input)


def test_navegacao_no_menu_mantem_sessao_autenticada(monkeypatch):
    at = _autenticar(_novo_app(monkeypatch))

    # 1ª troca de página: a limpeza de estado roda — `auth_ok` precisa sobreviver.
    at.button(key=f"nav_{_GRUPO}_0").click().run()
    assert "auth_ok" in at.session_state and at.session_state["auth_ok"] is True, (
        "a limpeza da troca de página apagou a marca de autenticação"
    )

    # 2ª troca de página: era aqui que o portão voltava a pedir a senha.
    at.button(key=f"nav_{_GRUPO}_1").click().run()
    assert not _tem_tela_de_senha(at), "o HUB voltou a pedir a senha ao navegar"
    assert not at.exception
