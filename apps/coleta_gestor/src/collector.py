"""Coleta headless dos dados do gestor escolar — MODO LEITURA.

Módulo sem Streamlit: expõe o `CONFIG` da etapa, o módulo que monta o artefato
(`zipper`, aqui o `exporter`) e o worker executado pela rodada da Coleta
Automática. Nenhuma escrita é feita no site Educacenso (cláusula pétrea).
"""

from __future__ import annotations

from apps.common import ui

from . import exporter as zipper

CONFIG: dict = {
    "key": "gestor",
    "form_key": "configuracao_gestor",
    "state_prefix": "cg_",
    "arquivo_key": "xlsx",
    "construtor_arquivo": "build_xlsx",
    "botao_arquivo": "Baixar XLSX",
    "mime_arquivo": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "zip_prefix": "vinculo_gestor",
    "title": "Dados dos Gestores Escolares",
    "subtitle": (
        "Coleta os dados do vínculo do gestor escolar no Educacenso, em modo leitura "
        "(não altera dados preenchidos)."
    ),
    "subtitle_sem_logo": "Extração em modo leitura dos vínculos do gestor (INEP).",
    "aviso_sem_arquivo_persistente": False,
}


def scrape_worker(config, login, senha, escolas, stop_event, lock, shared, tmp_dir):
    """Thread de coleta do gestor (assinatura "config primeiro" da rodada).

    ``config`` não é usado por esta etapa; a assinatura é a mesma das demais,
    para o runner chamar todos os workers do mesmo jeito.
    """
    from . import gestor_scraper

    def _chamar_coleta(browser, login, senha, escolas, on_progress=None, stop_check=None,
                       on_school_done=None):
        return gestor_scraper.run_scraping(
            browser, login, senha, escolas,
            on_progress=on_progress, stop_check=stop_check, on_school_done=on_school_done,
        )

    def _gravar(escola, dados):
        zipper.append_school_temp(dados, tmp_dir)

    return ui.worker_base(
        login, senha, escolas, stop_event, lock, shared,
        chamar_coleta=_chamar_coleta, gravar=_gravar,
    )
