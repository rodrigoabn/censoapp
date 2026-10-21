"""Coleta headless dos recibos de fechamento — MODO LEITURA.

Módulo sem Streamlit: expõe o `CONFIG` da etapa (de `config.py`), o módulo que
monta o artefato (`zipper`) e o worker executado pela rodada da Coleta
Automática. Nenhuma escrita é feita no site Educacenso.
"""

from __future__ import annotations

from apps.common import ui

from . import zipper
from .config import CONFIG

__all__ = ["CONFIG", "scrape_worker"]


def scrape_worker(config, login, senha, escolas, stop_event, lock, shared, tmp_dir):
    """Thread de coleta dos recibos (assinatura "config primeiro" da rodada)."""
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
