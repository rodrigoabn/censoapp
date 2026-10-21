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
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

from apps.common.orientacoes import card_orientacoes
from apps.common.school_list import read_school_list
from apps.common.ui import (
    RELOGIO_CSS,
    _duracao,
    _relogio_andamento_html,
    _relogio_resumo_html,
    linha_monitor,
    status_color,
)

from .etapas import ETAPAS
from .runner import executar_rodada

_TITULO = "Coleta Automática"
_SUBTITULO = "Executa em sequência as coletas do Educacenso, em segundo plano."

#: Cor da situação de cada etapa na tabela.
_COR_SITUACAO = {
    "concluida": "#22c55e",
    "concluida_sem_dados": "#eab308",
    "em_andamento": "#93c5fd",
    "falhou": "#ef4444",
    "interrompida": "#eab308",
    "pendente": "#8b8f99",
    "nao_executada": "#8b8f99",
}

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


def _mime_do_arquivo(nome: str) -> str:
    """MIME pelo sufixo do artefato (XLSX, XLS ou ZIP)."""
    baixo = nome.lower()
    if baixo.endswith(".xlsx"):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if baixo.endswith(".xls"):
        return "application/vnd.ms-excel"
    if baixo.endswith(".zip"):
        return "application/zip"
    return "application/octet-stream"


def _botao_download(caminho: str, rotulo: str, chave: str) -> None:
    """Botão de download que só lê o arquivo no clique (data como callable)."""
    arquivo = Path(caminho)
    st.download_button(
        rotulo,
        data=lambda c=arquivo: c.read_bytes(),
        file_name=arquivo.name,
        mime=_mime_do_arquivo(arquivo.name),
        key=chave,
        use_container_width=True,
    )


def _tabela_etapas(resultados: list) -> None:
    """A tabela "Tempo por aplicação"."""
    st.markdown("**Tempo por aplicação**")
    for resultado in resultados:
        (
            col_etapa,
            col_situacao,
            col_tempo,
            col_resultado,
            col_download,
        ) = st.columns([3, 1.6, 1, 2.6, 1])
        with col_etapa:
            st.markdown(resultado.titulo)
        with col_situacao:
            cor = _COR_SITUACAO.get(resultado.situacao, "#b2b5be")
            st.markdown(
                f"<span style='color:{cor}'>{resultado.situacao.replace('_', ' ')}</span>",
                unsafe_allow_html=True,
            )
        with col_tempo:
            st.markdown(f"`{_duracao(resultado.segundos)}`")
        with col_resultado:
            if resultado.motivo:
                st.markdown(
                    f"<span style='color:#ef4444'>{resultado.motivo}</span>",
                    unsafe_allow_html=True,
                )
            elif resultado.caminho_artefato:
                st.markdown(f"`{Path(resultado.caminho_artefato).name}`")
            else:
                st.markdown("—")
        with col_download:
            if resultado.caminho_artefato:
                _botao_download(
                    resultado.caminho_artefato,
                    "Baixar",
                    f"ca_dl_{resultado.chave}",
                )
                if resultado.caminho_pendencias:
                    _botao_download(
                        resultado.caminho_pendencias,
                        "Pendências",
                        f"ca_dl_pend_{resultado.chave}",
                    )


def _tela_rodada() -> None:
    """Estado 1/1b: a rodada em andamento (ou pausada aguardando o usuário)."""
    ss = st.session_state
    estado = ss.get("ca_estado") or {}
    inicio = ss.get("ca_inicio")

    if inicio is not None:
        st.markdown(
            _relogio_andamento_html(
                (datetime.now() - inicio).total_seconds(), inicio
            ),
            unsafe_allow_html=True,
        )

    _tabela_etapas(estado.get("resultados") or [])

    # Linha viva: a escola que a etapa em curso está coletando.
    atual = (estado.get("shared_etapa") or {}).get("current")
    if atual:
        _i, _total, nome, codigo = atual
        st.markdown(
            linha_monitor(
                f"{nome} ({codigo}): coletando…", status_color("Coletando dados ...")
            ),
            unsafe_allow_html=True,
        )

    aguardando = estado.get("aguardando")
    if aguardando:
        st.warning(
            f"A etapa **{aguardando}** não coletou nenhuma escola. "
            "Deseja continuar com as próximas?"
        )
        col_continuar, col_encerrar = st.columns(2)
        with col_continuar:
            if st.button(
                "Continuar", key="ca_continuar", use_container_width=True
            ):
                ss["ca_continuar"].set()
        with col_encerrar:
            if st.button(
                "Encerrar a rodada", key="ca_encerrar", use_container_width=True
            ):
                ss["ca_stop"].set()
    else:
        if st.button("⛔ Interromper rodada", key="ca_interromper"):
            ss["ca_stop"].set()

    time.sleep(0.5)
    st.rerun()


def _tela_resultado() -> None:
    """Estado 2/3: a rodada terminou (ou foi interrompida)."""
    ss = st.session_state
    estado = ss.get("ca_estado") or {}
    inicio = ss.get("ca_inicio")
    fim = ss.get("ca_fim")

    if inicio is not None and fim is not None:
        st.markdown(
            _relogio_resumo_html(inicio, fim), unsafe_allow_html=True
        )

    _tabela_etapas(estado.get("resultados") or [])

    pacote = estado.get("pacote")
    if pacote:
        with st.container(border=True):
            st.markdown("**Pacote completo**")
            _botao_download(pacote[0], "Baixar ZIP com todas as coletas", "ca_pacote")
    else:
        st.markdown(
            "<span style='color:#ef4444'>Rodada interrompida — o pacote completo "
            "não é gerado.</span>",
            unsafe_allow_html=True,
        )
        st.caption(
            "As etapas concluídas continuam baixáveis acima, arquivo por arquivo."
        )

    if st.button("Nova rodada", key="ca_nova_rodada"):
        for chave in (
            "ca_running",
            "ca_finalized",
            "ca_estado",
            "ca_pasta",
            "ca_fim",
        ):
            ss.pop(chave, None)
        st.rerun()


def render_coleta_automatica_frontend(logo_base64: str | None = None) -> None:
    """Tela da Coleta Automática (HUB)."""
    from apps.common.banner import banner_titulo

    ss = st.session_state
    st.markdown(RELOGIO_CSS, unsafe_allow_html=True)
    banner_titulo(st, _TITULO, _SUBTITULO, logo_base64)

    estado = ss.get("ca_estado") or {}
    if estado.get("terminada") and ss.get("ca_running"):
        # A thread da rodada acabou: fecha o estado e mostra o resultado.
        ss["ca_running"] = False
        ss["ca_finalized"] = True
        ss["ca_fim"] = datetime.now()
        st.rerun()

    if ss.get("ca_running"):
        _tela_rodada()
        return
    if ss.get("ca_finalized"):
        _tela_resultado()
        return
    _tela_formulario()
