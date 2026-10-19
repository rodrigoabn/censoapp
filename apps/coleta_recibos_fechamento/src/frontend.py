"""Frontend (Streamlit) da COLETA DE RECIBOS DE FECHAMENTO — MODO LEITURA.

Coleta: login, senha e upload da lista de escolas. Dispara a coleta (apenas
leitura no site) e, ao final, disponibiliza os recibos (PDF) de cada escola
compactados em um único arquivo ZIP para download. Nenhuma escrita é feita no
site Educacenso.

Fase 4.6: o corpo vive em `apps.common.ui`; aqui ficam os wrappers finos que
preservam os nomes históricos e amarram as bases aos globais deste módulo
(o `st` patcheável e os callbacks `_scrape_worker`/`_monitor`/`_finalize`).
"""

from __future__ import annotations

import streamlit as st

from apps.common import ui

from . import zipper
from .config import CONFIG

_TEXTOS = ui.TextosFrontend(
    item="recibo",
    ajuda_final=(
        "- Ao concluir, os recibos (PDF) de todas as escolas ficam disponíveis em um "
        "único **arquivo ZIP** para download."
    ),
    indisponiveis=("Recibo de fechamento indisponível.",),
)


def _ctx() -> ui.FrontendCtx:
    """Amarra as bases comuns aos globais deste módulo (patch-friendly)."""
    return ui.FrontendCtx(
        st=st,
        zipper=zipper,
        textos=_TEXTOS,
        scrape_worker=_scrape_worker,
        monitor=_monitor,
        finalize=_finalize,
        start=_start_scraping,
    )


def _ensure_chromium():
    """Wrapper de `apps.common.ui` (histórico): garante o Chromium no processo."""
    return ui.ensure_chromium()


def _chromium_already_installed() -> bool:
    """Wrapper de `apps.common.ui` (histórico): checagem de instalação prévia."""
    return ui.chromium_already_installed()


_SUBMIT_CSS = ui.SUBMIT_CSS


def _init_state(p: str):
    """Wrapper de `apps.common.ui` (histórico): estado inicial da tela."""
    return ui.init_state(p, st=st)


def _escapar(valor) -> str:
    """Wrapper de `apps.common.ui` (histórico)."""
    return ui.escapar(valor)


def _linha_monitor(texto: str, cor: str) -> str:
    """Wrapper de `apps.common.ui` (histórico)."""
    return ui.linha_monitor(texto, cor)


def _status_color(estado: str) -> str:
    """Wrapper de `apps.common.ui` (histórico): tupla vermelha do Recibos."""
    return ui.status_color(estado, _TEXTOS.indisponiveis)


def _scrape_worker(config, login, senha, escolas, stop_event, lock, shared, tmp_dir):
    """Wrapper de `apps.common.ui` (histórico): thread de coleta dos recibos."""
    from . import receipt_scraper

    def _chamar_coleta(browser, login, senha, escolas, on_progress=None, stop_check=None,
                       on_school_done=None):
        return receipt_scraper.run_receipt_scraping(
            browser, login, senha, escolas, config["url"],
            on_progress=on_progress, stop_check=stop_check, on_school_done=on_school_done,
        )

    def _gravar(escola, dados):
        zipper.append_pdf(escola["codigo_inep"], escola.get("nome_unidade", ""), dados, tmp_dir)

    return ui.worker_base(
        login, senha, escolas, stop_event, lock, shared,
        chamar_coleta=_chamar_coleta, gravar=_gravar,
    )


def _start_scraping(config: dict, login: str, senha: str, escolas: list[dict]) -> None:
    """Wrapper de `apps.common.ui` (histórico): dispara a coleta."""
    return ui.start_base(config, login, senha, escolas, ctx=_ctx())


def _monitor(config: dict) -> None:
    """Wrapper de `apps.common.ui` (histórico): monitor de progresso."""
    return ui.monitor_base(config, ctx=_ctx())


def _finalize(config: dict, count: int) -> None:
    """Wrapper de `apps.common.ui` (histórico): gera o ZIP e os pendentes."""
    return ui.finalize_base(config, count, ctx=_ctx())


def render_receipt_frontend(logo_base64=None):
    """Wrapper de `apps.common.ui` (histórico): tela da coleta de recibos."""
    return ui.render_coleta_frontend(CONFIG, logo_base64, ctx=_ctx())