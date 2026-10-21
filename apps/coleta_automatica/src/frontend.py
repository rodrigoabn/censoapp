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
from datetime import datetime
from pathlib import Path

import streamlit as st

from apps.common.banner import banner_titulo
from apps.common.orientacoes import card_orientacoes
from apps.common.school_list import read_school_list
from apps.common.ui import (
    RELOGIO_CSS,
    _duracao,
    _relogio_andamento_conteudo_html,
    _relogio_resumo_conteudo_html,
    ensure_chromium,
    escapar,
    linha_monitor,
    status_color,
)

from .etapas import ETAPAS
from .runner import (
    SITUACOES,
    executar_rodada,
    limpar_temporarios_antigos,
)

_TITULO = "Coleta de Dados no Educacenso - 1ª Etapa"
_SUBTITULO = "Executa em sequência as coletas do Educacenso, em segundo plano."

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

#: Estilo da tabela de resultados e dos botões de download.
TABELA_CSS = """
<style>
/* Cartão do relógio: o botão fica à direita, no meio da altura. */
[data-testid="stMain"] [class*="st-key-ca_relogio"] [data-testid="stColumn"]:last-child {
    display: flex !important;
    align-items: center !important;
    justify-content: flex-end !important;
}
/* Botões do cartão do relógio: a mesma linguagem do relógio digital
   (contorno fino, azul do mostrador e o brilho dele). */
[data-testid="stMain"] [class*="st-key-ca_relogio"] .stButton > button {
    background-color: transparent !important;
    border: 1px solid var(--relogio-azul) !important;
    color: var(--relogio-azul) !important;
    font-weight: 600 !important;
    text-shadow: var(--relogio-brilho);
}
[data-testid="stMain"] [class*="st-key-ca_relogio"] .stButton > button:hover {
    background-color: rgba(147, 197, 253, 0.12) !important;
    box-shadow: 0 0 14px rgba(147, 197, 253, 0.25) !important;
}
/* Tempo e nome do arquivo em fonte monoespaçada. */
[data-testid="stMain"] .relogio-mono {
    font-family: Consolas, 'Courier New', monospace !important;
    font-size: 0.82rem;
    color: #e4e6ec !important;
}
/* Download dos dados: verde fosco (borda e texto). */
[data-testid="stMain"] [class*="st-key-ca_dl_dados_"] button {
    background-color: transparent !important;
    border: 1px solid #4a8a63 !important;
    color: #93d6ac !important;
    font-size: 0.78rem !important;
    padding: 0.35rem 0.8rem !important;
}
[data-testid="stMain"] [class*="st-key-ca_dl_dados_"] button:hover {
    background-color: rgba(74, 138, 99, 0.18) !important;
}
/* Download das pendências: vermelho fosco (borda e texto). */
[data-testid="stMain"] [class*="st-key-ca_dl_pend_"] button {
    background-color: transparent !important;
    border: 1px solid #9c4a4a !important;
    color: #e5a3a3 !important;
    font-size: 0.78rem !important;
    padding: 0.35rem 0.8rem !important;
}
[data-testid="stMain"] [class*="st-key-ca_dl_pend_"] button:hover {
    background-color: rgba(156, 74, 74, 0.18) !important;
}
</style>
"""


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


def _botao_download(
    caminho: str,
    rotulo: str,
    chave: str,
    largura: str = "stretch",
) -> None:
    """Botão de download que só lê o arquivo no clique (data como callable)."""
    arquivo = Path(caminho)
    st.download_button(
        rotulo,
        data=lambda c=arquivo: c.read_bytes(),
        file_name=arquivo.name,
        mime=_mime_do_arquivo(arquivo.name),
        key=chave,
        width=largura,
    )


#: Larguras das colunas da tabela de resultados.
LARGURAS = [2, 1.3, 1.1, 3.2, 1.3, 1.5]

#: Cabeçalho da tabela de resultados.
CABECALHO = ["Tipo de dados", "Status", "Tempo", "Arquivo", "Dados", "Pendências"]

#: Ícone (bolinha colorida) de cada situação da tabela.
ICONES = {
    "concluida": "🟢",
    "concluida_sem_dados": "🟡",
    "em_andamento": "🔵",
    "pendente": "🟡",
    "falhou": "🔴",
    "interrompida": "🟠",
    "nao_executada": "⚪",
}
assert set(ICONES) == set(SITUACOES), "situação sem ícone na tabela"


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

    with st.container(border=True):
        st.subheader("Tempo por aplicação")

        # Cabeçalho: rótulo curto e discreto em cada coluna.
        for coluna, titulo in zip(st.columns(LARGURAS), CABECALHO):
            coluna.caption(f"**{titulo}**")
        st.divider()

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

            colunas = st.columns(LARGURAS, vertical_alignment="center")
            with colunas[0]:
                st.write(etapa.titulo)
            with colunas[1]:
                icone = ICONES.get(situacao, "⚪")
                rotulo = _ROTULO_SITUACAO.get(situacao, situacao)
                st.write(f"{icone} {rotulo}")
            with colunas[2]:
                st.markdown(
                    f"<span class='relogio-mono'>{_duracao(segundos)}</span>",
                    unsafe_allow_html=True,
                )
            with colunas[3]:
                if motivo:
                    st.markdown(
                        f"<span style='color:#ef4444'>{escapar(motivo)}</span>",
                        unsafe_allow_html=True,
                    )
                elif artefato:
                    st.markdown(
                        f"<span class='relogio-mono'>"
                        f"{escapar(Path(artefato).name)}</span>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.write("—")
            with colunas[4]:
                if artefato:
                    _botao_download(
                        artefato,
                        "Baixar",
                        f"ca_dl_dados_{etapa.chave}",
                        largura="content",
                    )
            with colunas[5]:
                if pendencias:
                    _botao_download(
                        pendencias,
                        "Baixar",
                        f"ca_dl_pend_{etapa.chave}",
                        largura="content",
                    )
            st.divider()


def _cartao_relogio(estado: dict, inicio) -> None:
    """Cartão do relógio da rodada: tempo, início da coleta e os botões.

    O botão de interromper (ou de continuar/parar, quando a rodada está
    pausada) fica **dentro** do cartão do relógio, à direita.
    """
    ss = st.session_state
    aguardando = estado.get("aguardando")

    with st.container(border=True, key="ca_relogio"):
        col_relogio, col_botao = st.columns([5, 1.7], vertical_alignment="center")
        with col_relogio:
            if inicio is not None:
                st.markdown(
                    _relogio_andamento_conteudo_html(
                        (datetime.now() - inicio).total_seconds(),
                        inicio,
                        alinhamento="flex-end",
                    ),
                    unsafe_allow_html=True,
                )
        with col_botao:
            if aguardando:
                if st.button("Continuar", key="ca_continuar", width="stretch"):
                    ss["ca_continuar_event"].set()
                if st.button(
                    "Encerrar a rodada", key="ca_encerrar", width="stretch"
                ):
                    ss["ca_stop"].set()
            elif st.button(
                "⛔ Interromper rodada", key="ca_interromper", width="content"
            ):
                ss["ca_stop"].set()

        # Escola que está sendo coletada no momento.
        atual = (estado.get("shared_etapa") or {}).get("current")
        if atual:
            _i, _total, nome, codigo = atual
            st.markdown(
                linha_monitor(
                    f"Escola atual: {nome} ({codigo}): coletando…",
                    status_color("Coletando dados ..."),
                ),
                unsafe_allow_html=True,
            )

        # Nova tentativa: o portal estourou timeout e a MESMA escola está sendo
        # repetida na hora — a fila só segue quando as tentativas terminarem
        # (as escolas já coletadas ficam preservadas).
        aviso = (estado.get("shared_etapa") or {}).get("aviso")
        if aviso:
            codigo, nome, texto = aviso
            st.markdown(
                linha_monitor(
                    f"{nome} ({codigo}): {texto}…",
                    status_color("Nova tentativa"),
                ),
                unsafe_allow_html=True,
            )

        # Aviso de pausa: a etapa rodou sem coletar nada.
        if aguardando:
            titulo = _titulo_da_etapa(aguardando)
            st.warning(
                f"A etapa **{titulo}** não coletou nenhuma escola. "
                "Deseja continuar com as próximas?"
            )


def _tela_rodada(estado: dict) -> None:
    """Desenha a rodada em andamento: o cartão do relógio e a tabela.

    O redesenho periódico é feito pelo fragmento :func:`_fragmento_rodada`.
    """
    inicio = st.session_state.get("ca_inicio")
    comecou = estado.get("etapa_inicio")
    segundos_atual = (
        (datetime.now() - comecou).total_seconds() if comecou else 0.0
    )

    # Cartão do relógio (com os botões da rodada dentro).
    _cartao_relogio(estado, inicio)

    _tabela_etapas(
        estado.get("resultados") or [],
        _etapas_selecionadas(estado),
        estado.get("etapa_atual"),
        segundos_atual,
    )


@st.fragment(run_every=0.5)
def _fragmento_rodada() -> None:
    """A tela da rodada, redesenhada a cada 0,5s.

    O redesenho usa um **fragmento** e não `sleep` + `st.rerun()`: abortar o
    script no meio da execução deixava a árvore de elementos do frontend com
    restos da tela anterior (as "Orientações" e o card "SELECIONE O QUE
    DESEJA COLETAR" reapareciam junto com a rodada). O fragmento limpa e
    redesenha apenas os elementos dele, a cada ciclo.
    """
    ss = st.session_state
    estado = _ler_estado(ss)

    if estado.get("terminada") and ss.get("ca_running"):
        # A thread da rodada acabou: fecha o estado e redesenha a página.
        ss["ca_running"] = False
        ss["ca_finalized"] = True
        ss["ca_fim"] = datetime.now()
        st.rerun()

    _tela_rodada(estado)


def _tela_resultado() -> None:
    """Estado 2/3: a rodada terminou (ou foi interrompida)."""
    ss = st.session_state
    estado = _ler_estado(ss)
    inicio = ss.get("ca_inicio")
    fim = ss.get("ca_fim")

    if inicio is not None and fim is not None:
        with st.container(border=True, key="ca_resumo"):
            st.markdown(
                _relogio_resumo_conteudo_html(inicio, fim),
                unsafe_allow_html=True,
            )

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

    clicado = False
    with st.container(border=True):
        st.markdown("**SELECIONE O QUE DESEJA COLETAR**")
        col_esq, col_dir = st.columns(2)
        for coluna, grupo in zip((col_esq, col_dir), (ETAPAS[:3], ETAPAS[3:])):
            with coluna:
                for etapa in grupo:
                    st.checkbox(
                        etapa.titulo, key=f"ca_sel_{etapa.chave}", value=True
                    )

        selecionadas = _selecionadas()
        st.caption(f"{len(selecionadas)} de {len(ETAPAS)} aplicações selecionadas.")
        clicado = st.button(
            "Executar", type="primary", key="ca_executar", use_container_width=True
        )

    # O rerun da rodada sai **fora** do card: um `st.rerun()` de dentro de
    # um container deixa o card aberto e o frontend passa a exibir o resto
    # do formulário (Orientações e "SELECIONE O QUE DESEJA COLETAR") junto
    # com a tela da rodada.
    if clicado:
        _iniciar_rodada(selecionadas, login, senha, arquivo)


def render_coleta_automatica_frontend(logo_base64: str | None = None) -> None:
    """Tela da Coleta Automática (HUB)."""
    ss = st.session_state
    st.markdown(RELOGIO_CSS, unsafe_allow_html=True)
    st.markdown(TABELA_CSS, unsafe_allow_html=True)
    banner_titulo(st, _TITULO, _SUBTITULO, logo_base64)

    estado = _ler_estado(ss)
    if estado.get("terminada") and ss.get("ca_running"):
        # A thread da rodada acabou: fecha o estado e mostra o resultado.
        ss["ca_running"] = False
        ss["ca_finalized"] = True
        ss["ca_fim"] = datetime.now()
        st.rerun()

    if ss.get("ca_running"):
        _fragmento_rodada()
        return
    if ss.get("ca_finalized"):
        _tela_resultado()
        return
    _tela_formulario()
