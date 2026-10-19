"""Tela inicial (Streamlit) — COLETA DE DADOS DO GESTOR ESCOLAR.

Coleta: login, senha e upload da lista de escolas.
Dispara o scraping (apenas leitura no site) e, ao final, disponibiliza o
arquivo XLSX consolidado (aba "Vínculo do gestor") para download. Nenhuma
escrita é feita no site Educacenso (cláusula pétrea de modo leitura).

Fase 4.7: o corpo vive em `apps.common.ui`; aqui ficam os wrappers finos que
preservam os nomes históricos e amarram as bases aos globais deste módulo
(o `st` patcheável e os callbacks `_scrape_worker`/`_monitor`/`_finalize`).
"""

from __future__ import annotations

import streamlit as st

from apps.common import ui

from . import exporter

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

_TEXTOS = ui.TextosFrontend(
    item="escola",
    ajuda_final=(
        "- Ao concluir, o arquivo **XLSX consolidado** (aba \"Vínculo do gestor\") "
        "fica disponível para download."
    ),
    modo_leitura=(
        "- **Modo leitura:** a aplicação apenas navega e lê o site; "
        "não altera dados no INEP."
    ),
    msg_interrompido=(
        "Coleta interrompida. {count} escola(s) coletada(s) no arquivo "
        "'{nome_arquivo}'. A escola em andamento foi descartada; as demais foram "
        "marcadas como não coletadas."
    ),
    msg_vazio="Arquivo XLSX não gerado. Motivo: Nenhuma escola coletada.",
    msg_erro_build="Falha ao gerar o XLSX: {exc}",
    msg_pendentes="{n} escola(s) não tiveram dados coletados.",
)


def _ctx() -> ui.FrontendCtx:
    """Amarra as bases comuns aos globais deste módulo (patch-friendly).

    A base comum fala a convenção "config primeiro"; os adaptadores
    `*_com_config` fazem a ponte para os wrappers históricos deste app (que
    não recebem `config`) lendo o global correspondente no call time.
    """
    return ui.FrontendCtx(
        st=st,
        zipper=exporter,
        textos=_TEXTOS,
        scrape_worker=_scrape_worker_com_config,
        monitor=_monitor_com_config,
        finalize=_finalize_com_config,
        start=_start_com_config,
    )


def _ensure_chromium():
    """Wrapper de `apps.common.ui` (histórico): garante o Chromium no processo."""
    return ui.ensure_chromium()


def _chromium_already_installed() -> bool:
    """Wrapper de `apps.common.ui` (histórico): checagem de instalação prévia."""
    return ui.chromium_already_installed()


_SUBMIT_CSS = ui.SUBMIT_CSS


def _init_state():
    """Wrapper de `apps.common.ui` (histórico): estado inicial da tela."""
    return ui.init_state(CONFIG["state_prefix"], st=st)


def _escapar(valor) -> str:
    """Wrapper de `apps.common.ui` (histórico)."""
    return ui.escapar(valor)


def _linha_monitor(texto: str, cor: str) -> str:
    """Wrapper de `apps.common.ui` (histórico)."""
    return ui.linha_monitor(texto, cor)


def _status_color(estado: str) -> str:
    """Wrapper de `apps.common.ui` (histórico): tupla vermelha do Gestor."""
    return ui.status_color(estado, _TEXTOS.indisponiveis)


def _scrape_worker(login, senha, escolas, stop_event, lock, shared, tmp_dir):
    """Wrapper de `apps.common.ui` (histórico): thread de coleta do gestor."""
    from . import gestor_scraper

    def _chamar_coleta(browser, login, senha, escolas, on_progress=None, stop_check=None,
                       on_school_done=None):
        return gestor_scraper.run_scraping(
            browser, login, senha, escolas,
            on_progress=on_progress, stop_check=stop_check, on_school_done=on_school_done,
        )

    def _gravar(escola, dados):
        exporter.append_school_temp(dados, tmp_dir)

    return ui.worker_base(
        login, senha, escolas, stop_event, lock, shared,
        chamar_coleta=_chamar_coleta, gravar=_gravar,
    )


def _scrape_worker_com_config(config, login, senha, escolas, stop_event, lock, shared, tmp_dir):
    """Adaptador do ctx: descarta o `config` e chama o worker histórico."""
    return _scrape_worker(login, senha, escolas, stop_event, lock, shared, tmp_dir)


def _start_scraping(login: str, senha: str, escolas: list[dict]) -> None:
    """Wrapper de `apps.common.ui` (histórico): dispara a coleta."""
    return ui.start_base(CONFIG, login, senha, escolas, ctx=_ctx())


def _start_com_config(config: dict, login: str, senha: str, escolas: list[dict]) -> None:
    """Adaptador do ctx: repassa o `config` da tela para a base comum."""
    return ui.start_base(config, login, senha, escolas, ctx=_ctx())


def _monitor() -> None:
    """Wrapper de `apps.common.ui` (histórico): monitor de progresso."""
    return ui.monitor_base(CONFIG, ctx=_ctx())


def _monitor_com_config(config: dict) -> None:
    """Adaptador do ctx: repassa o `config` da tela para a base comum."""
    return ui.monitor_base(config, ctx=_ctx())


def _finalize(count: int) -> None:
    """Wrapper de `apps.common.ui` (histórico): gera o XLSX e os pendentes."""
    return ui.finalize_base(CONFIG, count, ctx=_ctx())


def _finalize_com_config(config: dict, count: int) -> None:
    """Adaptador do ctx: repassa o `config` da tela para a base comum."""
    return ui.finalize_base(config, count, ctx=_ctx())


def render_gestor_frontend(logo_base64=None):
    """Wrapper de `apps.common.ui` (histórico): tela da coleta do gestor."""
    return ui.render_coleta_frontend(CONFIG, logo_base64, ctx=_ctx())
