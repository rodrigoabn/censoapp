"""A tela da Coleta Automática.

Estados da tela:

- **formulário** — credenciais, lista de escolas e seleção das aplicações;
- **rodada em andamento** — relógio digital e tabela com o tempo por etapa;
- **rodada pausada** — uma etapa rodou sem coletar nada: a tela pergunta se
  a rodada deve continuar;
- **rodada concluída** — resumo dos tempos e pacote completo;
- **rodada interrompida** — o pacote completo não é gerado.

A tela **não** usa ``st.form``: o botão "Executar" fica no fim das opções
selecionáveis e o contador de selecionadas precisa atualizar a cada clique.
"""

from __future__ import annotations

import tempfile
import threading
from datetime import datetime
from pathlib import Path

import streamlit as st

from apps.common.orientacoes import card_orientacoes
from apps.common.school_list import read_school_list
from apps.common.ui import RELOGIO_CSS

from .etapas import ETAPAS
from .runner import executar_rodada

_TITULO = "Coleta Automática"
_SUBTITULO = "Executa em sequência as coletas do Educacenso, em segundo plano."

_ORIENTACOES = (
    "1. Informe seu **Login (CPF)** e **Senha** de acesso ao Educacenso.\n"
    "2. Envie a **lista de escolas** (.xlsx / .xls) com as colunas "
    "*código do inep* e *nome da unidade*.\n"
    "3. Marque as **aplicações** que entram na rodada.\n"
    "4. Clique em **Executar**: as coletas rodam em sequência, em segundo plano.\n"
    "5. Ao final, baixe cada arquivo ou o **pacote completo**."
)


def _selecionadas() -> list:
    """Etapas marcadas pelo usuário (todas, por padrão)."""
    ss = st.session_state
    return [e for e in ETAPAS if ss.get(f"ca_sel_{e.chave}", True)]


def _iniciar_rodada(selecionadas: list, login: str, senha: str, arquivo) -> None:
    """Valida a entrada e sobe a thread da rodada."""
    ss = st.session_state

    if not selecionadas:
        st.error("Selecione ao menos uma aplicação para coletar.")
        return
    if not (login and senha):
        st.error("Preencha login e senha.")
        return
    if arquivo is None:
        st.error("Envie a lista de escolas.")
        return
    try:
        escolas = read_school_list(arquivo)
    except ValueError as exc:
        st.error(str(exc))
        return
    if not escolas:
        st.error("A lista de escolas não contém escolas válidas.")
        return

    stop_event = threading.Event()
    continuar_event = threading.Event()
    lock = threading.Lock()
    pasta = Path(tempfile.mkdtemp(prefix="coleta_automatica_tmp_"))
    estado = {
        "resultados": [],
        "etapa_atual": None,
        "shared_etapa": None,
        "aguardando": None,
        "interrompida": False,
        "pacote": None,
    }

    ss["ca_stop"] = stop_event
    ss["ca_continuar"] = continuar_event
    ss["ca_lock"] = lock
    ss["ca_pasta"] = pasta
    ss["ca_estado"] = estado
    ss["ca_inicio"] = datetime.now()
    ss["ca_fim"] = None
    ss["ca_running"] = True
    ss["ca_finalized"] = False

    thread = threading.Thread(
        target=executar_rodada,
        args=(tuple(selecionadas), login, senha, escolas),
        kwargs={
            "stop_event": stop_event,
            "lock": lock,
            "estado": estado,
            "pasta_base": pasta,
            "continuar_event": continuar_event,
        },
        daemon=True,
    )
    ss["ca_thread"] = thread
    thread.start()
    st.rerun()


def _tela_formulario() -> None:
    """Estado 0: credenciais, lista de escolas e seleção das aplicações."""

    with st.container(border=True):
        card_orientacoes(st, corpo=_ORIENTACOES)

    with st.container(border=True):
        col_login, col_senha, col_arquivo = st.columns(3)
        with col_login:
            login = st.text_input("Login (CPF)", key="ca_login")
        with col_senha:
            senha = st.text_input("Senha", type="password", key="ca_senha")
        with col_arquivo:
            arquivo = st.file_uploader(
                "Lista de escolas (.xlsx / .xls)",
                type=["xlsx", "xls"],
                key="ca_lista",
            )

    with st.container(border=True):
        st.markdown("**Aplicações a coletar**")
        st.caption("Desmarque o que não deve entrar nesta rodada.")
        col_esq, col_dir = st.columns(2)
        for coluna, grupo in zip((col_esq, col_dir), (ETAPAS[:3], ETAPAS[3:])):
            with coluna:
                for etapa in grupo:
                    st.checkbox(
                        etapa.titulo, key=f"ca_sel_{etapa.chave}", value=True
                    )

        selecionadas = _selecionadas()
        st.caption(f"{len(selecionadas)} de {len(ETAPAS)} aplicações selecionadas.")
        if st.button(
            "Executar", type="primary", key="ca_executar", use_container_width=True
        ):
            _iniciar_rodada(selecionadas, login, senha, arquivo)


def render_coleta_automatica_frontend(logo_base64: str | None = None) -> None:
    """Tela da Coleta Automática (HUB)."""
    from apps.common.banner import banner_titulo

    st.markdown(RELOGIO_CSS, unsafe_allow_html=True)
    banner_titulo(st, _TITULO, _SUBTITULO, logo_base64)
    _tela_formulario()
