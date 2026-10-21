"""Coleta headless dos relatórios CSV (turmas, alunos, profissionais).

Módulo sem Streamlit: expõe o módulo que monta o artefato (`zipper`) e o
worker parametrizado pelo config do relatório (``REPORTS``), executado pela
rodada da Coleta Automática. Nenhuma escrita é feita no site Educacenso.
"""

from __future__ import annotations

from apps.common import ui

from . import zipper


def scrape_worker(config, login, senha, escolas, stop_event, lock, shared, tmp_dir):
    """Thread de coleta dos relatórios (assinatura "config primeiro" da rodada)."""
    from . import report_scraper

    def _chamar_coleta(browser, login, senha, escolas, on_progress=None, stop_check=None,
                       on_school_done=None):
        return report_scraper.run_report_scraping(
            browser, login, senha, escolas, config["url"],
            on_progress=on_progress, stop_check=stop_check, on_school_done=on_school_done,
        )

    def _gravar(escola, dados):
        zipper.append_csv(escola["codigo_inep"], escola.get("nome_unidade", ""), dados, tmp_dir)

    return ui.worker_base(
        login, senha, escolas, stop_event, lock, shared,
        chamar_coleta=_chamar_coleta, gravar=_gravar,
    )
