"""Componentes compartilhados dos frontends de coleta (Streamlit) — Fase 4.

Bases genéricas parametrizadas por `FrontendCtx`: cada app mantém wrappers
finos que preservam os nomes históricos e entregam os globais do próprio
módulo (o `st` do app e os callbacks `_scrape_worker`/`_monitor`/`_finalize`),
para que os monkeypatches dos testes continuem valendo.

Nenhuma base escreve no Educacenso (cláusula pétrea de modo leitura); aqui só
há tela, estado de sessão e orquestração da thread de coleta.
"""

from __future__ import annotations

import html
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import streamlit as st

from apps.common.school_list import read_school_list


@dataclass(frozen=True)
class TextosFrontend:
    """Textos próprios do app usados pelas bases comuns.

    Os templates usam `.format()`; os defaults são exatamente os textos
    históricos do app de Relatórios.
    """

    item: str = "relatório"              # "{n} relatório(s)"; "não tiveram relatório coletado"
    ajuda_final: str = ""                # bullet final do card de orientações
    indisponiveis: tuple[str, ...] = ()  # estados "vermelhos" extras do app
    modo_leitura: str = (                # primeiro bullet do card de orientações
        "- **Modo leitura:** a aplicação apenas navega e baixa os relatórios do site; "
        "não altera dados no INEP."
    )
    msg_concluido: str = (
        "Concluído. {count} {item}(s) no arquivo '{nome_arquivo}', pronto para download."
    )
    msg_interrompido: str = (
        "Coleta interrompida. {count} {item}(s) no arquivo '{nome_arquivo}'. "
        "A escola em andamento foi descartada; as demais foram marcadas como não coletadas."
    )
    msg_vazio: str = "Arquivo Zip não gerado. Motivo: Nenhum {item} disponível para download."
    msg_erro_build: str = "Falha ao gerar o ZIP: {exc}"
    msg_pendentes: str = "{n} escola(s) não tiveram {item} coletado."


@dataclass(frozen=True)
class FrontendCtx:
    """Amarrações do módulo do app, lidas no call time (monkeypatch-friendly)."""

    st: Any
    zipper: Any
    textos: TextosFrontend
    scrape_worker: Callable
    monitor: Callable
    finalize: Callable
    start: Callable


SUBMIT_CSS = """
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


def chromium_already_installed() -> bool:
    """True se o Chromium do Playwright já está no cache (evita reinstalar)."""
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


@st.cache_resource(show_spinner="Preparando navegador (primeira execução)...")
def ensure_chromium():
    """Garante o Chromium do Playwright no processo (instala só se faltar)."""
    if chromium_already_installed():
        return True
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=True,
    )
    return True


def escapar(valor) -> str:
    """Escapa texto dinâmico (nome de escola etc.) antes de entrar em HTML."""
    return html.escape(str(valor))


def linha_monitor(texto: str, cor: str) -> str:
    """Monta a linha colorida do monitor, com o texto sempre escapado."""
    return f"<span style='color:{cor}'>{escapar(texto)}</span>"


def status_color(estado: str, indisponiveis: tuple[str, ...] = ()) -> str:
    """Cor do estado no monitor (a tupla vermelha extra é de cada app)."""
    if estado == "concluído":
        return "#22c55e"  # verde (--status-ok)
    if estado.startswith("erro") or estado.startswith("Falha no login") or estado in indisponiveis:
        return "#ef4444"  # vermelho (--status-danger)
    return "#b2b5be"      # neutro (em andamento / interrompido)


def init_state(p: str, *, st: Any = st) -> None:
    """Inicializa as chaves de estado do app (idempotente, via setdefault)."""
    ss = st.session_state
    ss.setdefault(f"{p}running", False)
    ss.setdefault(f"{p}stop", None)
    ss.setdefault(f"{p}lock", None)
    ss.setdefault(f"{p}shared", None)
    ss.setdefault(f"{p}thread", None)
    ss.setdefault(f"{p}finalized", False)
    ss.setdefault(f"{p}zip", None)
    ss.setdefault(f"{p}pending", None)


def worker_base(
    login: str,
    senha: str,
    escolas: list[dict],
    stop_event: threading.Event,
    lock: threading.Lock,
    shared: dict,
    *,
    chamar_coleta: Callable,
    gravar: Callable,
) -> None:
    """Thread de coleta genérica.

    Não acessa `st.*` (thread-safety): comunica-se apenas via `shared` (dict
    plano protegido por `lock`). `chamar_coleta` encadeia o `run_*` do app (com
    a URL quando houver) e `gravar` persiste UMA escola concluída nos
    temporários — a escola em andamento no momento da parada é descartada.
    """
    from playwright.sync_api import sync_playwright

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
                _outputs, failures = chamar_coleta(
                    browser,
                    login,
                    senha,
                    escolas,
                    on_progress=hook,
                    stop_check=stop_event.is_set,
                    on_school_done=gravar,
                )
            finally:
                browser.close()

        with lock:
            shared["failures"] = failures
    except Exception as exc:  # noqa: BLE001
        with lock:
            shared["error"] = str(exc)
    finally:
        with lock:
            shared["done"] = True


def start_base(config: dict, login: str, senha: str, escolas: list[dict], *, ctx: FrontendCtx) -> None:
    """Prepara temporários/estado e dispara a thread de coleta do app."""
    p = config["state_prefix"]
    pasta = ctx.zipper.nova_pasta_temporaria()

    stop_event = threading.Event()
    lock = threading.Lock()
    shared: dict = {
        "current": None, "last": None, "count": 0,
        "total": len(escolas), "done": False, "error": None,
        "interrupted": False, "failures": [],
    }

    thread = threading.Thread(
        target=ctx.scrape_worker,
        args=(config, login, senha, escolas, stop_event, lock, shared, pasta),
        daemon=True,
    )

    ss = ctx.st.session_state
    ss[f"{p}stop"] = stop_event
    ss[f"{p}lock"] = lock
    ss[f"{p}shared"] = shared
    ss[f"{p}thread"] = thread
    ss[f"{p}running"] = True
    ss[f"{p}finalized"] = False
    ss[f"{p}{config.get('arquivo_key', 'zip')}"] = None
    ss[f"{p}pending"] = None
    ss[f"{p}tmp_dir"] = pasta

    thread.start()


def monitor_base(config: dict, *, ctx: FrontendCtx) -> None:
    """Monitor de progresso genérico (finaliza e re-renderiza quando acaba)."""
    st = ctx.st
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

    # Coleta encerrada: finaliza e re-renderiza (o formulário com os downloads
    # persistentes volta à tela; o monitor sai de cena por inteiro).
    if done:
        ctx.finalize(config, count)
        st.rerun()
        return

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
            linha_monitor(
                f"{nome} ({codigo}): Coletando dados ...",
                status_color("Coletando dados ...", ctx.textos.indisponiveis),
            ),
            unsafe_allow_html=True,
        )
    if last:
        i, tot, nome, codigo, estado = last
        st.markdown(
            linha_monitor(
                f"Escola {i}/{tot} — {nome} ({codigo}): {estado}",
                status_color(estado, ctx.textos.indisponiveis),
            ),
            unsafe_allow_html=True,
        )

    time.sleep(0.5)
    st.rerun()


def finalize_base(config: dict, count: int, *, ctx: FrontendCtx) -> None:
    """Finalização genérica: arquivo principal, pendentes e limpeza.

    O artefato principal é parametrizado pelo `config` (defaults = app de
    Relatórios): `arquivo_key` (sufixo da chave de sessão), `construtor_arquivo`
    (função do módulo de exportação), `botao_arquivo`/`mime_arquivo` (download)
    e `zip_prefix` (prefixo do nome do arquivo).
    """
    st = ctx.st
    zipper = ctx.zipper
    textos = ctx.textos
    ss = st.session_state
    p = config["state_prefix"]
    chave = config.get("arquivo_key", "zip")
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
            construtor = getattr(zipper, config.get("construtor_arquivo", "build_zip"))
            arquivo_bytes = construtor(tmp_dir=ss[f"{p}tmp_dir"])
            nome_arquivo = zipper.output_filename(config["zip_prefix"])
            ss[f"{p}{chave}"] = (arquivo_bytes, nome_arquivo)

            if interrupted:
                st.success(
                    textos.msg_interrompido.format(
                        count=count, item=textos.item, nome_arquivo=nome_arquivo
                    )
                )
            else:
                st.success(
                    textos.msg_concluido.format(
                        count=count, item=textos.item, nome_arquivo=nome_arquivo
                    )
                )

            st.download_button(
                label=config.get("botao_arquivo", "Baixar ZIP"),
                data=arquivo_bytes,
                file_name=nome_arquivo,
                mime=config.get("mime_arquivo", "application/zip"),
                key=f"{p}download",
            )
        else:
            # Nenhum arquivo coletado: não gera o principal; limpa temporários.
            zipper.remover_temp(ss[f"{p}tmp_dir"])
            ss[f"{p}{chave}"] = None
            st.markdown(
                "<span style='color:#ef4444'>"
                + textos.msg_vazio.format(item=textos.item)
                + "</span>",
                unsafe_allow_html=True,
            )

        # Planilha (download separado) com as escolas processadas que falharam.
        if failures:
            pending_bytes = zipper.build_pending_xlsx(failures)
            pending_nome = zipper.pending_filename(config["zip_prefix"])
            ss[f"{p}pending"] = (pending_bytes, pending_nome)
            st.markdown(
                "<span style='color:#ef4444'>"
                + textos.msg_pendentes.format(n=len(failures), item=textos.item)
                + "</span>",
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
        st.error(textos.msg_erro_build.format(exc=exc))


def render_coleta_frontend(config: dict, logo_base64=None, *, ctx: FrontendCtx):
    """Tela genérica da coleta: banner, formulário, downloads persistentes."""
    st = ctx.st
    textos = ctx.textos
    p = config["state_prefix"]
    chave = config.get("arquivo_key", "zip")
    st.markdown(SUBMIT_CSS, unsafe_allow_html=True)
    ensure_chromium()
    init_state(p, st=st)

    # ── Banner (tema HUB) ───────────────────────────────────────────────────
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
            <p>{config.get('subtitle_sem_logo') or config['subtitle']}</p>
        </div>"""
    st.markdown(banner_html, unsafe_allow_html=True)

    # Coleta em andamento: exibe monitor/progresso e botão de interrupção.
    if st.session_state[f"{p}running"]:
        ctx.monitor(config)
        return

    col_form, col_help = st.columns([1.4, 1])

    with col_form:
        st.markdown('<div class="custom-card">', unsafe_allow_html=True)
        with st.form(config.get("form_key") or f"config_{config['key']}"):
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
        st.markdown(f"""
        {textos.modo_leitura}
        - Informe seu **Login (CPF)** e **Senha** de acesso ao Educacenso.
        - Envie a **lista de escolas** (.xlsx / .xls) com as colunas *código do inep* e *nome da unidade*.
        {textos.ajuda_final}
        """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # Download persistente de uma coleta anterior já finalizada.
    if st.session_state[f"{p}finalized"]:
        if st.session_state[f"{p}{chave}"]:
            arquivo_bytes, nome_arquivo = st.session_state[f"{p}{chave}"]
            st.download_button(
                label=config.get("botao_arquivo", "Baixar ZIP"),
                data=arquivo_bytes,
                file_name=nome_arquivo,
                mime=config.get("mime_arquivo", "application/zip"),
                key=f"{p}download_persist",
            )
        elif config.get("aviso_sem_arquivo_persistente", True):
            st.markdown(
                "<span style='color:#ef4444'>"
                + textos.msg_vazio.format(item=textos.item)
                + "</span>",
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

    ctx.start(config, login, senha, escolas)
    st.rerun()
