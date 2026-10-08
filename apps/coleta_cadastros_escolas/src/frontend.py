"""Tela inicial (Streamlit) — MODO LEITURA.

Coleta: login, senha e upload da lista de escolas.
Dispara o scraping (apenas leitura no site) e, ao final, disponibiliza o
arquivo XLSX consolidado para download. Nenhuma escrita é feita no site
Educacenso nem em Planilha Google (cláusula pétrea).
"""

from __future__ import annotations

import base64
import subprocess
import sys
import threading
import time
from pathlib import Path

import streamlit as st


@st.cache_resource(show_spinner="Preparando navegador (primeira execução)...")
def _ensure_chromium():
    """Garante que o Chromium do Playwright esteja disponível.

    Só executa o download quando o navegador ainda não está presente no cache,
    evitando reexecutar `playwright install` (e seu aviso "OS not officially
    supported") a cada cold start no Streamlit Community Cloud. As bibliotecas
    de sistema são providas via packages.txt.
    """
    if _chromium_already_installed():
        return True
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=True,
    )
    return True


def _chromium_already_installed() -> bool:
    """Infere o caminho de instalação via `playwright install --dry-run` e
    verifica se o executável do Chromium já existe no cache."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "--dry-run", "chromium"],
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:  # noqa: BLE001
        return False

    install_dir = None
    for line in result.stdout.splitlines():
        if "Install location:" in line:
            install_dir = line.split("Install location:", 1)[1].strip()
            break
    if not install_dir:
        return False

    base = Path(install_dir)
    candidates = (
        base / "chrome-linux64" / "chrome",
        base / "chrome-linux" / "chrome",
    )
    return any(candidate.exists() for candidate in candidates)

from src.upload import read_school_list
from src import exporter


# Estilo escopado mínimo para destacar o botão de submissão dentro do tema do HUB.
_SUBMIT_CSS = """
<style>
[data-testid="stFormSubmitButton"] button {
    background-color: var(--status-info) !important;
    border-color: var(--status-info) !important;
    color: #ffffff !important;
}
[data-testid="stFormSubmitButton"] button:hover {
    background-color: #2f6fe0 !important;
}
</style>
"""


def _init_state():
    ss = st.session_state
    ss.setdefault("ws_running", False)
    ss.setdefault("ws_stop", None)
    ss.setdefault("ws_lock", None)
    ss.setdefault("ws_shared", None)
    ss.setdefault("ws_thread", None)
    ss.setdefault("ws_finalized", False)
    ss.setdefault("ws_xlsx", None)


def render_frontend(logo_base64=None):
    st.markdown(_SUBMIT_CSS, unsafe_allow_html=True)
    _ensure_chromium()
    _init_state()

    # ── Banner (tema HUB) ────────────────────────────────────────────────────
    if logo_base64:
        banner_html = f"""
        <div class="title-container" style="display:flex; align-items:center; gap:1.5rem;">
            <img src="data:image/png;base64,{logo_base64}"
                 style="width:68px; height:68px; border-radius:12px;
                        box-shadow:0 4px 12px rgba(0,0,0,0.2);
                        background:#fff; padding:5px;" />
            <div>
                <h1 style="margin:0; padding:0; line-height:1.2; color:white !important;">
                    Dados Cadastrais da Unidades
                </h1>
                <p style="margin-top:0.3rem; color:#bfdbfe; font-size:1rem; margin-bottom:0;">
                    Coleta os dados cadastrais das escolas no Educacenso, em modo leitura (não altera dados preenchidos).
                </p>
            </div>
        </div>"""
    else:
        banner_html = """
        <div class="title-container">
            <h1>Dados Cadastrais da Unidades</h1>
            <p>Extração em modo leitura das fichas de escolas (INEP).</p>   
        </div>"""
    st.markdown(banner_html, unsafe_allow_html=True)

    # Coleta em andamento: exibe monitor/progresso e botão de interrupção.
    if st.session_state.ws_running:
        _monitor()
        return

    col_form, col_help = st.columns([1.4, 1])

    with col_form:
        st.markdown('<div class="custom-card">', unsafe_allow_html=True)
        with st.form("configuracao"):
            login = st.text_input("Login (CPF)", help="Usuário de acesso ao Educacenso.")
            senha = st.text_input("Senha", type="password")
            arquivo = st.file_uploader(
                "Lista de escolas (.xlsx / .xls)",
                type=["xlsx", "xls"],
                help="Deve conter as colunas: 'código do inep' e 'nome da unidade'.",
            )
            submitted = st.form_submit_button("Iniciar extração")
        st.markdown('</div>', unsafe_allow_html=True)

    with col_help:
        st.markdown('<div class="custom-card">', unsafe_allow_html=True)
        st.markdown("""
        <h3>Orientações de uso</h3>
        <div class="badge badge-warning">Atenção</div>
        Esta aplicação não guarda em nenhum arquivo o seu Login e Senha de acesso ao Educacenso.
        """, unsafe_allow_html=True)
        st.markdown("""
        - **Modo leitura:** a aplicação apenas navega e lê o site; não altera dados no INEP.
        - Informe seu **Login (CPF)** e **Senha** de acesso ao Educacenso.
        - Envie a **lista de escolas** (.xlsx / .xls) com as colunas *código do inep* e *nome da unidade*.
        - Ao concluir, o arquivo **XLSX consolidado** fica disponível para download.
        """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # Download persistente de uma coleta anterior já finalizada.
    if st.session_state.ws_finalized and st.session_state.ws_xlsx:
        xlsx_bytes, nome_arquivo = st.session_state.ws_xlsx
        st.download_button(
            label="Baixar XLSX",
            data=xlsx_bytes,
            file_name=nome_arquivo,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="ws_download_persist",
        )

    if not submitted:
        return

    if not (login and senha and arquivo):
        st.error("Preencha login, senha e envie a lista de escolas.")
        return

    try:
        escolas = read_school_list(arquivo)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Falha ao ler a lista de escolas: {exc}")
        return

    if not escolas:
        st.error("Nenhuma escola válida encontrada no arquivo.")
        return

    _start_scraping(login, senha, escolas)
    st.rerun()


def _scrape_worker(login, senha, escolas, stop_event, lock, shared):
    """Executa a coleta em thread de background.

    NÃO acessa `st.*` (thread-safety). Comunica-se apenas via `shared` (dict
    plano protegido por `lock`). Grava nos temporários apenas as escolas
    concluídas — a escola em andamento no momento da parada é descartada.
    """
    from playwright.sync_api import sync_playwright
    from src.scraper import run_scraping

    def hook(i, total, codigo, nome, estado):
        with lock:
            shared["total"] = total
            if estado == "Coletando dados ...":
                shared["current"] = (i, total, nome, codigo)
            else:
                shared["last"] = (i, total, nome, codigo, estado)
                shared["current"] = None
                if estado == "concluído":
                    shared["count"] = shared.get("count", 0) + 1

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                outputs = run_scraping(
                    browser, login, senha, escolas,
                    on_progress=hook, stop_check=stop_event.is_set,
                )
            finally:
                browser.close()

        for _, dados in outputs:
            try:
                exporter.append_school_temp(dados)
            except Exception as exc:  # noqa: BLE001
                with lock:
                    shared.setdefault("warnings", []).append(str(exc))
    except Exception as exc:  # noqa: BLE001
        with lock:
            shared["error"] = str(exc)
    finally:
        with lock:
            shared["done"] = True


def _start_scraping(login: str, senha: str, escolas: list[dict]) -> None:
    exporter.reset_temp()

    stop_event = threading.Event()
    lock = threading.Lock()
    shared: dict = {
        "current": None, "last": None, "count": 0,
        "total": len(escolas), "done": False, "error": None,
        "interrupted": False,
    }

    thread = threading.Thread(
        target=_scrape_worker,
        args=(login, senha, escolas, stop_event, lock, shared),
        daemon=True,
    )

    st.session_state.ws_stop = stop_event
    st.session_state.ws_lock = lock
    st.session_state.ws_shared = shared
    st.session_state.ws_thread = thread
    st.session_state.ws_running = True
    st.session_state.ws_finalized = False
    st.session_state.ws_xlsx = None

    thread.start()


def _monitor() -> None:
    ss = st.session_state
    lock = ss.ws_lock
    shared = ss.ws_shared

    with lock:
        current = shared.get("current")
        last = shared.get("last")
        count = shared.get("count", 0)
        total = shared.get("total", 0)
        done = shared.get("done", False)
        error = shared.get("error")

    # Botão de interrupção.
    if not ss.ws_stop.is_set():
        if st.button("⛔ Interromper coleta", key="ws_stop_btn"):
            ss.ws_stop.set()
            st.warning(
                "Interrupção solicitada. Finalizando a escola em andamento "
                "(ela será descartada) e gerando o arquivo..."
            )
    else:
        st.warning("Interrompendo... aguarde a finalização segura da coleta.")

    # Progresso e linhas de status (mantém o padrão de duas linhas).
    frac = (count / total) if total else 0.0
    st.progress(min(frac, 1.0))

    if current:
        i, tot, nome, codigo = current
        st.write(f"{nome} ({codigo}): Coletando dados ...")
    if last:
        i, tot, nome, codigo, estado = last
        st.write(f"Escola {i}/{tot} — {nome} ({codigo}): {estado}")

    if done:
        _finalize(count)
        return

    time.sleep(0.5)
    st.rerun()


def _finalize(count: int) -> None:
    ss = st.session_state
    interrupted = ss.ws_stop.is_set() if ss.ws_stop else False

    with ss.ws_lock:
        error = ss.ws_shared.get("error")

    ss.ws_running = False

    if error:
        st.error(f"Falha na coleta: {error}")

    try:
        xlsx_bytes = exporter.build_xlsx()
        nome_arquivo = exporter.output_filename()
        ss.ws_xlsx = (xlsx_bytes, nome_arquivo)
        ss.ws_finalized = True

        if interrupted:
            st.success(
                f"Coleta interrompida. {count} escola(s) coletada(s) no arquivo "
                f"'{nome_arquivo}'. A escola em andamento foi descartada."
            )
        else:
            st.success(
                f"Concluído. {count} escola(s) no arquivo '{nome_arquivo}', "
                "pronto para download."
            )

        st.download_button(
            label="Baixar XLSX",
            data=xlsx_bytes,
            file_name=nome_arquivo,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="ws_download",
        )
    except Exception as exc:  # noqa: BLE001
        st.error(f"Falha ao gerar o XLSX: {exc}")
