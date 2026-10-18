"""Portão de autenticação do HUB.

Modos, detectados pela configuração e forçáveis por `CENSO_AUTH_MODE`:

- ``oidc``   — SSO nativo do Streamlit (seção ``[auth]`` em secrets.toml);
  modo de produção na intranet. Fecha por padrão se ``[auth]`` não existir.
- ``senha``  — senha única compartilhada (seção ``[auth_simples]``); fallback
  do MVP apenas enquanto não houver OIDC disponível.
- ``aberto`` — sem autenticação; uso local/desenvolvimento (mostra aviso).

O portão é aplicado uma única vez no topo do ``app.py``, antes de qualquer
render: quem não está autenticado recebe a tela de entrada e ``st.stop()``.
"""

from __future__ import annotations

import hmac
import os

MODOS = ("oidc", "senha", "aberto")
_ENV_MODO = "CENSO_AUTH_MODE"
_CHAVE_SESSAO = "auth_ok"

_ROTULO_ENTRAR = "Entrar"
_ROTULO_SAIR = "Sair"
_LABEL_SENHA = "Senha de acesso"


def _secrets_dict(st) -> dict:
    """Lê ``st.secrets`` como dict; ambiente sem secrets não pode quebrar aqui."""
    try:
        secrets = st.secrets
        if hasattr(secrets, "to_dict"):
            return secrets.to_dict()
        return dict(secrets)
    except Exception:
        return {}


def modo_autenticacao(secrets, env=None) -> str:
    """Resolve o modo vigente a partir do ambiente e da configuração.

    ``CENSO_AUTH_MODE`` (env) tem precedência quando informado; um valor fora
    de ``MODOS`` é erro de configuração (ValueError com a lista de aceitos).
    """
    env = dict(os.environ) if env is None else env
    forcado = env.get(_ENV_MODO)
    if forcado:
        if forcado not in MODOS:
            raise ValueError(
                f"{_ENV_MODO} inválido: {forcado!r}. Use um de: {', '.join(MODOS)}."
            )
        return forcado
    if "auth" in secrets:
        return "oidc"
    if "auth_simples" in secrets:
        return "senha"
    return "aberto"


def _rotulo_usuario(st) -> str:
    """Melhor rótulo disponível do usuário logado (e-mail > nome > genérico)."""
    email = getattr(st.user, "email", None)
    nome = getattr(st.user, "name", None)
    return email or nome or "sessão autenticada"


def _render_usuario(st, rotulo: str, revogar) -> None:
    """Mostra quem está autenticado na sidebar e oferece o botão "Sair"."""
    st.sidebar.markdown(f"🔐 Autenticado: **{rotulo}**")
    if st.sidebar.button(_ROTULO_SAIR, key="auth_sair"):
        revogar()
        st.rerun()


def _render_pagina_login(st) -> None:
    """Página mínima de entrada (o app só renderiza depois do login)."""
    st.markdown("## Aplicações de Apoio — Censo Escolar")
    st.caption(
        "Acesso restrito à intranet da SEDUCT. Entre com sua conta institucional."
    )
    if st.button(_ROTULO_ENTRAR, key="auth_entrar"):
        st.login()


def _revoga_senha(st):
    """Revogação da sessão no modo "senha" (a flag vive no session_state)."""

    def _revogar() -> None:
        st.session_state[_CHAVE_SESSAO] = False

    return _revogar


def exigir_autenticacao(st, env=None) -> None:
    """Aplica o portão de acesso: chame 1× no topo do app, antes de renderizar."""
    secrets = _secrets_dict(st)
    modo = modo_autenticacao(secrets, env)

    if modo == "aberto":
        st.sidebar.caption("Modo local — autenticação não configurada.")
        return

    if modo == "oidc":
        if "auth" not in secrets:
            st.error(
                "Autenticação OIDC forçada (CENSO_AUTH_MODE=oidc), mas a seção "
                "[auth] não está configurada em .streamlit/secrets.toml."
            )
            st.stop()
        if not getattr(st.user, "is_logged_in", False):
            _render_pagina_login(st)
            st.stop()
        _render_usuario(st, _rotulo_usuario(st), st.logout)
        return

    # modo == "senha"
    if st.session_state.get(_CHAVE_SESSAO):
        _render_usuario(st, "sessão autenticada", _revoga_senha(st))
        return

    senha = st.text_input(_LABEL_SENHA, type="password")
    if st.button(_ROTULO_ENTRAR, key="auth_entrar"):
        esperada = str(secrets.get("auth_simples", {}).get("senha", ""))
        if esperada and hmac.compare_digest(str(senha or ""), esperada):
            st.session_state[_CHAVE_SESSAO] = True
            return  # liberado: o app continua a renderizar nesta execução
        st.error("Senha incorreta.")
    st.stop()
