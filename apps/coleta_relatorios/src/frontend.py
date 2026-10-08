"""Frontend (Streamlit) das aplicações de COLETA DE RELATÓRIOS — MODO LEITURA.

Reutilizável pelas 3 aplicações (turmas, alunos, profissionais). Coleta:
login, senha e upload da lista de escolas. Dispara a coleta (apenas leitura no
site) e, ao final, disponibiliza os CSV de cada escola compactados em um único
arquivo ZIP para download. Nenhuma escrita é feita no site Educacenso.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time

import streamlit as st

from .upload import read_school_list
from . import zipper


@st.cache_resource(show_spinner="Preparando navegador (primeira execução)...")
def _ensure_chromium():
    """Baixa o Chromium do Playwright uma única vez por processo."""
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=True,
    )
    return True


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


def _init_state(p: str):
    ss = st.session_state
    ss.setdefault(f"{p}running", False)
    ss.setdefault(f"{p}stop", None)
    ss.setdefault(f"{p}lock", None)
    ss.setdefault(f"{p}shared", None)
    ss.setdefault(f"{p}thread", None)
    ss.setdefault(f"{p}finalized", False)
    ss.setdefault(f"{p}zip", None)
    ss.setdefault(f"{p}pending", None)


def render_report_frontend(config: dict, logo_base64=None):
    p = config["state_prefix"]
    st.markdown(_SUBMIT_CSS, unsafe_allow_html=True)
    _ensure_chromium()
    _init_state(p)

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
                    {config['title']}
                </h1>
                <p style="margin-top:0.3rem; color:#bfdbfe; font-size:1rem; margin-bottom:0;">
                    {config['subtitle']}
                </p>
            </div>
        </div>"""
    else:
        banner_html = f"""
        <div class="title-container">
            <h1>{config['title']}</h1>
            <p>{config['subtitle']}</p>
        </div>"""
    st.markdown(banner_html, unsafe_allow_html=True)

    # Coleta em andamento: exibe monitor/progresso e botão de interrupção.
    if st.session_state[f"{p}running"]:
        _monitor(config)
        return

    col_form, col_help = st.columns([1.4, 1])

    with col_form:
        st.markdown('<div class="custom-card">', unsafe_allow_html=True)
        with st.form(f"config_{config['key']}"):
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
        - **Modo leitura:** a aplicação apenas navega e baixa os relatórios do site; não altera dados no INEP.
        - Informe seu **Login (CPF)** e **Senha** de acesso ao Educacenso.
        - Envie a **lista de escolas** (.xlsx / .xls) com as colunas *código do inep* e *nome da unidade*.
        - Ao concluir, os CSV de todas as escolas ficam disponíveis em um único **arquivo ZIP** para download.
        """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # Download persistente de uma coleta anterior já finalizada.
    if st.session_state[f"{p}finalized"]:
        if st.session_state[f"{p}zip"]:
            zip_bytes, nome_arquivo = st.session_state[f"{p}zip"]
            st.download_button(
                label="Baixar ZIP",
                data=zip_bytes,
                file_name=nome_arquivo,
                mime="application/zip",
                key=f"{p}download_persist",
            )
        else:
            st.markdown(
                "<span style='color:#ef4444'>Arquivo Zip não gerado. "
                "Motivo: Nenhum relatório disponível para download.</span>",
                unsafe_allow_html=True,
            )
        if st.session_state[f"{p}pending"]:
            pending_bytes, pending_nome = st.session_state[f"{p}pending"]
            st.download_button(
                label="Baixar escolas não coletadas (XLSX)",
                data=pending_bytes,
                file_name=pending_nome,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"{p}download_pending_persist",
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

    _start_scraping(config, login, senha, escolas)
    st.rerun()


def _scrape_worker(config, login, senha, escolas, stop_event, lock, shared):
    """Executa a coleta em thread de background.

    NÃO acessa `st.*` (thread-safety). Comunica-se apenas via `shared` (dict
    plano protegido por `lock`). Grava nos temporários apenas as escolas
    concluídas — a escola em andamento no momento da parada é descartada.
    """
    from playwright.sync_api import sync_playwright
    from .report_scraper import run_report_scraping

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
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                outputs, failures = run_report_scraping(
                    browser, login, senha, escolas, config["url"],
                    on_progress=hook, stop_check=stop_event.is_set,
                )
            finally:
                browser.close()

        with lock:
            shared["failures"] = failures

        for escola, data in outputs:
            try:
                zipper.append_csv(escola["codigo_inep"], escola.get("nome_unidade", ""), data)
            except Exception as exc:  # noqa: BLE001
                with lock:
                    shared.setdefault("warnings", []).append(str(exc))
    except Exception as exc:  # noqa: BLE001
        with lock:
            shared["error"] = str(exc)
    finally:
        with lock:
            shared["done"] = True


def _start_scraping(config: dict, login: str, senha: str, escolas: list[dict]) -> None:
    p = config["state_prefix"]
    zipper.reset_temp()

    stop_event = threading.Event()
    lock = threading.Lock()
    shared: dict = {
        "current": None, "last": None, "count": 0,
        "total": len(escolas), "done": False, "error": None,
        "interrupted": False, "failures": [],
    }

    thread = threading.Thread(
        target=_scrape_worker,
        args=(config, login, senha, escolas, stop_event, lock, shared),
        daemon=True,
    )

    st.session_state[f"{p}stop"] = stop_event
    st.session_state[f"{p}lock"] = lock
    st.session_state[f"{p}shared"] = shared
    st.session_state[f"{p}thread"] = thread
    st.session_state[f"{p}running"] = True
    st.session_state[f"{p}finalized"] = False
    st.session_state[f"{p}zip"] = None
    st.session_state[f"{p}pending"] = None

    thread.start()


def _status_color(estado: str) -> str:
    if estado == "concluído":
        return "#22c55e"  # verde (--status-ok)
    if estado.startswith("erro") or estado.startswith("Falha no login") or estado in (
        "Relatório inexistente.", "Preenchimento não iniciado.",
    ):
        return "#ef4444"  # vermelho (--status-danger)
    return "#b2b5be"      # neutro (em andamento / interrompido)


def _monitor(config: dict) -> None:
    ss = st.session_state
    p = config["state_prefix"]
    lock = ss[f"{p}lock"]
    shared = ss[f"{p}shared"]

    with lock:
        current = shared.get("current")
        last = shared.get("last")
        count = shared.get("count", 0)
        total = shared.get("total", 0)
        done = shared.get("done", False)

    # Botão de interrupção.
    if not ss[f"{p}stop"].is_set():
        if st.button("⛔ Interromper coleta", key=f"{p}stop_btn"):
            ss[f"{p}stop"].set()
            st.warning(
                "Interrupção solicitada. Finalizando a escola em andamento "
                "(ela será descartada) e gerando o arquivo..."
            )
    else:
        st.warning("Interrompendo... aguarde a finalização segura da coleta.")

    # Progresso e linhas de status.
    frac = (count / total) if total else 0.0
    st.progress(min(frac, 1.0))

    if current:
        i, tot, nome, codigo = current
        st.markdown(
            f"<span style='color:{_status_color('Coletando dados ...')}'>"
            f"{nome} ({codigo}): Coletando dados ...</span>",
            unsafe_allow_html=True,
        )
    if last:
        i, tot, nome, codigo, estado = last
        st.markdown(
            f"<span style='color:{_status_color(estado)}'>"
            f"Escola {i}/{tot} — {nome} ({codigo}): {estado}</span>",
            unsafe_allow_html=True,
        )

    if done:
        _finalize(config, count)
        return

    time.sleep(0.5)
    st.rerun()


def _finalize(config: dict, count: int) -> None:
    ss = st.session_state
    p = config["state_prefix"]
    interrupted = ss[f"{p}stop"].is_set() if ss[f"{p}stop"] else False

    with ss[f"{p}lock"]:
        error = ss[f"{p}shared"].get("error")
        failures = ss[f"{p}shared"].get("failures", [])

    ss[f"{p}running"] = False

    if error:
        st.error(f"Falha na coleta: {error}")

    try:
        ss[f"{p}finalized"] = True

        if count > 0:
            zip_bytes = zipper.build_zip()
            nome_arquivo = zipper.output_filename(config["zip_prefix"])
            ss[f"{p}zip"] = (zip_bytes, nome_arquivo)

            if interrupted:
                st.success(
                    f"Coleta interrompida. {count} relatório(s) no arquivo "
                    f"'{nome_arquivo}'. A escola em andamento foi descartada."
                )
            else:
                st.success(
                    f"Concluído. {count} relatório(s) no arquivo '{nome_arquivo}', "
                    "pronto para download."
                )

            st.download_button(
                label="Baixar ZIP",
                data=zip_bytes,
                file_name=nome_arquivo,
                mime="application/zip",
                key=f"{p}download",
            )
        else:
            # Nenhum CSV coletado: não gera ZIP; limpa temporários.
            zipper.reset_temp()
            ss[f"{p}zip"] = None
            st.markdown(
                "<span style='color:#ef4444'>Arquivo Zip não gerado. "
                "Motivo: Nenhum relatório disponível para download.</span>",
                unsafe_allow_html=True,
            )

        # Planilha (download separado) com as escolas processadas que falharam.
        if failures:
            pending_bytes = zipper.build_pending_xlsx(failures)
            pending_nome = zipper.pending_filename(config["zip_prefix"])
            ss[f"{p}pending"] = (pending_bytes, pending_nome)
            st.markdown(
                f"<span style='color:#ef4444'>{len(failures)} escola(s) "
                "não tiveram relatório coletado.</span>",
                unsafe_allow_html=True,
            )
            st.download_button(
                label="Baixar escolas não coletadas (XLSX)",
                data=pending_bytes,
                file_name=pending_nome,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"{p}download_pending",
            )
    except Exception as exc:  # noqa: BLE001
        st.error(f"Falha ao gerar o ZIP: {exc}")
