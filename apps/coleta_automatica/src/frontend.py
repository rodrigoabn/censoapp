"""A tela da Coleta de Dados no Educacenso - 1ª Etapa (rodada automática).

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

import shutil
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

from apps.common.banner import banner_titulo
from apps.common.orientacoes import card_orientacoes
from apps.common.school_list import read_school_list
from apps.common.ui import (
    RELOGIO_CSS,
    _duracao,
    _relogio_andamento_html,
    _relogio_resumo_html,
    ensure_chromium,
    escapar,
    linha_monitor,
    status_color,
)

from .etapas import ETAPAS
from .runner import SITUACOES, executar_rodada, limpar_temporarios_antigos

_TITULO = "Coleta de Dados no Educacenso - 1ª Etapa"
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

#: Rótulo exibido de cada situação na tabela.
_ROTULO_SITUACAO = {
    "pendente": "Pendente",
    "em_andamento": "Em andamento",
    "concluida": "Concluída",
    "concluida_sem_dados": "Concluída (sem dados)",
    "falhou": "Falhou",
    "interrompida": "Interrompida",
    "nao_executada": "Não executada",
}
assert set(_ROTULO_SITUACAO) == set(SITUACOES), "situação sem rótulo na tabela"

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


def _titulo_da_etapa(chave: str) -> str:
    """Título legível de uma etapa (a chave é interna)."""
    for etapa in ETAPAS:
        if etapa.chave == chave:
            return etapa.titulo
    return chave


def _etapas_selecionadas(estado: dict) -> list:
    """As etapas escolhidas para a rodada, na ordem do registro."""
    chaves = estado.get("etapas_selecionadas") or []
    por_chave = {e.chave: e for e in ETAPAS}
    return [por_chave[c] for c in chaves if c in por_chave]


def _ler_estado(ss) -> dict:
    """Lê o estado da rodada sob o lock (evita uma leitura rasgada)."""
    lock = ss.get("ca_lock")
    estado = ss.get("ca_estado") or {}
    if lock is None:
        return estado
    with lock:
        return dict(estado)


def _limpar_pasta_da_rodada(ss) -> None:
    """Apaga a pasta de trabalho da rodada (artefatos e pendências)."""
    pasta = ss.get("ca_pasta")
    if pasta:
        shutil.rmtree(pasta, ignore_errors=True)


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
    except Exception as exc:  # noqa: BLE001 — planilha corrompida não pode derrubar a tela
        st.error(f"Falha ao ler a lista de escolas: {exc}")
        return
    if not escolas:
        st.error("A lista de escolas não contém escolas válidas.")
        return

    # A rodada anterior (se houver) libera o disco antes de começar a nova;
    # as pastas órfãs de rodadas abandonadas também são limpas.
    _limpar_pasta_da_rodada(ss)
    limpar_temporarios_antigos()

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
        "terminada": False,
        "etapas_selecionadas": [e.chave for e in selecionadas],
    }

    ss["ca_stop"] = stop_event
    ss["ca_continuar_event"] = continuar_event
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


def _tabela_etapas(
    resultados: list,
    selecionadas: list,
    etapa_atual: str | None,
    segundos_atual: float = 0.0,
) -> None:
    """A tabela "Tempo por aplicação".

    Mostra **todas** as etapas da rodada: as que já terminaram (com o
    resultado), a que está em andamento e as que ainda vão rodar.
    """
    por_chave = {r.chave: r for r in resultados}

    st.markdown("**Tempo por aplicação**")
    for etapa in selecionadas:
        resultado = por_chave.get(etapa.chave)
        if resultado is not None:
            situacao = resultado.situacao
            segundos = resultado.segundos
            motivo = resultado.motivo
            artefato = resultado.caminho_artefato
            pendencias = resultado.caminho_pendencias
        elif etapa.chave == etapa_atual:
            situacao = "em_andamento"
            segundos = segundos_atual
            motivo = None
            artefato = None
            pendencias = None
        else:
            situacao = "pendente"
            segundos = 0.0
            motivo = None
            artefato = None
            pendencias = None

        (
            col_etapa,
            col_situacao,
            col_tempo,
            col_resultado,
            col_download,
        ) = st.columns([3, 1.6, 1, 2.6, 1])
        with col_etapa:
            st.markdown(etapa.titulo)
        with col_situacao:
            cor = _COR_SITUACAO.get(situacao, "#b2b5be")
            st.markdown(
                f"<span style='color:{cor}'>"
                f"{_ROTULO_SITUACAO.get(situacao, situacao)}</span>",
                unsafe_allow_html=True,
            )
        with col_tempo:
            st.markdown(f"`{_duracao(segundos)}`")
        with col_resultado:
            if motivo:
                st.markdown(
                    f"<span style='color:#ef4444'>{escapar(motivo)}</span>",
                    unsafe_allow_html=True,
                )
            elif artefato:
                st.markdown(f"`{Path(artefato).name}`")
            else:
                st.markdown("—")
        with col_download:
            if artefato:
                _botao_download(artefato, "Baixar", f"ca_dl_{etapa.chave}")
                if pendencias:
                    _botao_download(
                        pendencias, "Pendências", f"ca_dl_pend_{etapa.chave}"
                    )


def _tela_rodada() -> None:
    """Estado 1/1b: a rodada em andamento (ou pausada aguardando o usuário)."""
    ss = st.session_state
    estado = _ler_estado(ss)
    inicio = ss.get("ca_inicio")

    if inicio is not None:
        st.markdown(
            _relogio_andamento_html(
                (datetime.now() - inicio).total_seconds(), inicio
            ),
            unsafe_allow_html=True,
        )

    selecionadas = _etapas_selecionadas(estado)
    etapa_atual = estado.get("etapa_atual")
    comecou = estado.get("etapa_inicio")
    segundos_atual = (
        (datetime.now() - comecou).total_seconds() if comecou else 0.0
    )
    _tabela_etapas(
        estado.get("resultados") or [],
        selecionadas,
        etapa_atual,
        segundos_atual,
    )

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
        titulo = _titulo_da_etapa(aguardando)
        st.warning(
            f"A etapa **{titulo}** não coletou nenhuma escola. "
            "Deseja continuar com as próximas?"
        )
        col_continuar, col_encerrar = st.columns(2)
        with col_continuar:
            if st.button("Continuar", key="ca_continuar", use_container_width=True):
                ss["ca_continuar_event"].set()
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
    estado = _ler_estado(ss)
    inicio = ss.get("ca_inicio")
    fim = ss.get("ca_fim")

    if inicio is not None and fim is not None:
        st.markdown(_relogio_resumo_html(inicio, fim), unsafe_allow_html=True)

    _tabela_etapas(
        estado.get("resultados") or [],
        _etapas_selecionadas(estado),
        None,
    )

    erro = estado.get("erro_rodada")
    if erro:
        st.markdown(
            f"<span style='color:#ef4444'>Falha na rodada: {escapar(erro)}</span>",
            unsafe_allow_html=True,
        )

    pacote = estado.get("pacote")
    if pacote:
        with st.container(border=True):
            st.markdown("**Pacote completo**")
            _botao_download(pacote[0], "Baixar ZIP com todas as coletas", "ca_pacote")
    elif estado.get("interrompida"):
        st.markdown(
            "<span style='color:#ef4444'>Rodada interrompida — o pacote completo "
            "não é gerado.</span>",
            unsafe_allow_html=True,
        )
        st.caption(
            "As etapas concluídas continuam baixáveis acima, arquivo por arquivo."
        )
    else:
        st.caption("Nenhuma etapa produziu arquivo, então não há pacote para baixar.")

    if st.button("Nova rodada", key="ca_nova_rodada"):
        for chave in (
            "ca_running",
            "ca_finalized",
            "ca_estado",
            "ca_fim",
        ):
            ss.pop(chave, None)
        _limpar_pasta_da_rodada(ss)
        ss.pop("ca_pasta", None)
        st.rerun()


def _tela_formulario() -> None:
    """Estado 0: credenciais, lista de escolas e seleção das aplicações."""
    # Garante o navegador do Playwright (o mesmo das outras coletas).
    ensure_chromium()

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
    ss = st.session_state
    st.markdown(RELOGIO_CSS, unsafe_allow_html=True)
    banner_titulo(st, _TITULO, _SUBTITULO, logo_base64)

    estado = _ler_estado(ss)
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
