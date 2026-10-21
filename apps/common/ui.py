"""Componentes compartilhados das coletas: worker headless e relógio da rodada.

O ``worker_base`` roda a coleta numa thread sem tocar em ``st.*`` e é usado
pelos coletores headless (``collector.py`` de cada etapa). O relógio (CSS e
trechos HTML) é usado pela tela da Coleta de Dados.

Nenhuma base escreve no Educacenso (cláusula pétrea de modo leitura).
"""

from __future__ import annotations

import html
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

import streamlit as st

RELOGIO_CSS = """
<style>
/* Cores do relógio digital: azul do mostrador e o brilho dele. */
:root {
    --relogio-azul: #93c5fd;
    --relogio-brilho: 0 0 14px rgba(147, 197, 253, 0.35);
}
/* Relógio da coleta: digital (andamento) e resumo de tempos (conclusão) */
.stMarkdown div.relogio-caixa {
    background-color: var(--bg-card) !important;
    border: 1px solid var(--border-default) !important;
    border-radius: var(--radius-md) !important;
    padding: 14px 18px !important;
    margin-bottom: 1rem !important;
}
.stMarkdown div.relogio-titulo {
    font-family: 'Segoe UI', Tahoma, sans-serif !important;
    text-transform: uppercase;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 1.2px;
    color: var(--text-secondary) !important;
    margin-bottom: 0.6rem !important;
}
.stMarkdown div.relogio-rotulo {
    font-family: 'Segoe UI', Tahoma, sans-serif !important;
    text-transform: uppercase;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 1px;
    color: var(--text-secondary) !important;
    margin-bottom: 0.1rem !important;
}
.stMarkdown div.relogio-digital {
    font-family: Consolas, 'Courier New', monospace !important;
    font-size: 2.3rem;
    font-weight: 700;
    letter-spacing: 4px;
    line-height: 1.15;
    color: #93c5fd !important;
    text-shadow: 0 0 14px rgba(147, 197, 253, 0.35);
}
.stMarkdown div.relogio-valor {
    font-family: Consolas, 'Courier New', monospace !important;
    font-size: 1rem;
    font-weight: 700;
    color: #ffffff !important;
}
/* Botão de interromper a coleta: a mesma linguagem do relógio digital
   (contorno fino, azul do mostrador e o brilho dele). */
[data-testid="stMain"] [class*="stop_btn"] button {
    background-color: transparent !important;
    border: 1px solid var(--relogio-azul) !important;
    color: var(--relogio-azul) !important;
    font-weight: 600 !important;
    text-shadow: var(--relogio-brilho);
}
[data-testid="stMain"] [class*="stop_btn"] button:hover {
    background-color: rgba(147, 197, 253, 0.12) !important;
    box-shadow: 0 0 14px rgba(147, 197, 253, 0.25) !important;
}
</style>
"""


def _duracao(segundos: float) -> str:
    """Duração em HH:MM:SS."""
    total = int(max(0, segundos))
    horas, resto = divmod(total, 3600)
    minutos, segs = divmod(resto, 60)
    return f"{horas:02d}:{minutos:02d}:{segs:02d}"


def _horario(momento: datetime) -> str:
    """Horário no formato DD/MM/AAAA HH:MM:SS."""
    return momento.strftime("%d/%m/%Y %H:%M:%S")


def _relogio_andamento_conteudo_html(
    segundos: float,
    inicio: datetime,
    alinhamento: str = "center",
) -> str:
    """Conteúdo do relógio digital (sem a caixa), para usar num container.

    Quem usa desenha a borda com `st.container(border=True)` — assim o botão
    de interromper fica dentro do mesmo cartão do relógio.

    ``alinhamento`` é o `align-items` da linha: ``"flex-end"`` alinha os
    blocos pela base (o horário fica na linha do relógio).
    """
    return (
        f'<div style="display:flex; align-items:{alinhamento}; '
        'gap:2.4rem; flex-wrap:wrap;">'
        '<div>'
        '<div class="relogio-rotulo">Tempo em andamento</div>'
        f'<div class="relogio-digital">{_duracao(segundos)}</div>'
        '</div>'
        '<div>'
        '<div class="relogio-rotulo">Início da coleta</div>'
        f'<div class="relogio-valor">{_horario(inicio)}</div>'
        '</div>'
        '</div>'
    )


def _relogio_resumo_conteudo_html(inicio: datetime, fim: datetime) -> str:
    """Conteúdo do resumo de tempos (sem a caixa), para usar num container."""
    return (
        '<div style="display:flex; gap:2.6rem; flex-wrap:wrap; align-items:flex-end;">'
        '<div>'
        '<div class="relogio-rotulo">Horário inicial</div>'
        f'<div class="relogio-valor">{_horario(inicio)}</div>'
        '</div>'
        '<div>'
        '<div class="relogio-rotulo">Horário de término</div>'
        f'<div class="relogio-valor">{_horario(fim)}</div>'
        '</div>'
        '<div>'
        '<div class="relogio-rotulo">Tempo de execução</div>'
        f'<div class="relogio-valor">{_duracao((fim - inicio).total_seconds())}</div>'
        '</div>'
        '</div>'
    )


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


def status_color(estado: str) -> str:
    """Cor do estado da escola/etapa na tela da rodada."""
    if estado == "concluído":
        return "#22c55e"  # verde (--status-ok)
    if estado.startswith("erro"):
        return "#ef4444"  # vermelho (--status-danger)
    return "#b2b5be"      # neutro (em andamento / interrompido)


def registrar_progresso(
    shared: dict, lock, i: int, total: int, codigo: str, nome: str, estado: str
) -> None:
    """Atualiza o `shared` da coleta a partir de um evento de progresso.

    "Coletando dados ..." marca a escola atual; o aviso de nova tentativa por
    timeout fica em ``shared["aviso"]`` até a coleta recomeçar; os demais
    estados vão para ``shared["last"]`` (e "concluído" soma no contador).
    """
    with lock:
        shared["total"] = total
        if estado == "Coletando dados ...":
            shared["current"] = (i, total, nome, codigo)
            shared["aviso"] = None
        elif estado.startswith("nova tentativa"):
            shared["aviso"] = (codigo, nome, estado)
            shared["current"] = None
        else:
            shared["last"] = (i, total, nome, codigo, estado)
            shared["current"] = None
            shared["aviso"] = None
            if estado == "concluído":
                shared["count"] = shared.get("count", 0) + 1


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
        registrar_progresso(shared, lock, i, total, codigo, nome, estado)

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
            shared["fim"] = datetime.now()
            shared["done"] = True
