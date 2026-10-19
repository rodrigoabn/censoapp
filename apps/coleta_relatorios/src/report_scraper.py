"""Coleta de relatórios do Educacenso em MODO LEITURA (Playwright).

Fluxo por escola (apenas leitura/navegação):
  1. Login via Keycloak (acesso.inep.gov.br) com CPF + senha.
  2. Seleção da escola em /escola/pesquisar pelo código Inep (aceita o Termo
     de Sigilo se exibido — necessário apenas para acessar/navegar).
  3. Navega até a URL do relatório (turmas / alunos / profissionais).
  4. Clica em "Gerar relatório" -> "Gerar Excel" -> "CSV" e captura o
     download do arquivo CSV fornecido pelo próprio site.

NUNCA preenche, marca ou submete dados de questionário no site. A única saída
é o CSV que o próprio Educacenso disponibiliza para download.
"""

from __future__ import annotations

import logging

from playwright.sync_api import Browser, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from apps.common import browser as _browser
from apps.common import coleta as _coleta
from apps.common import session as _session

from .auth import _assert_read_only

logger = logging.getLogger("coleta_relatorios")


class PreenchimentoNaoIniciado(Exception):
    """Sinaliza que o relatório não pôde ser gerado porque a escola ainda não
    iniciou o preenchimento (botão 'Gerar relatório' indisponível)."""


class RelatorioInexistente(Exception):
    """Relatório não gerado: o site exibiu a snackbar de erro
    'Nenhum registro encontrado para essa pesquisa.' após 'Gerar relatório'."""


# Aliases de `apps.common` (Fase 4.3) — preservam os monkeypatches dos testes:
# os nomes continuam morando neste módulo e são lidos no call time.
LoginFalhou = _session.LoginFalhou
SessaoExpirada = _session.SessaoExpirada
_safe_cleanup = _browser.safe_cleanup
_wait_loader = _browser.wait_loader
_session_expirada = _browser.session_expirada


def _raise_if_expired(page: Page) -> None:
    """Levanta SessaoExpirada quando a página voltou para a tela de login."""
    # Mantida no módulo do app (não é alias): lê `_session_expirada` daqui para
    # os monkeypatches dos testes continuarem valendo.
    if _session_expirada(page):
        raise SessaoExpirada()


_login_and_read = _session.login_and_read
_accept_sigilo_if_present = _session.accept_sigilo_if_present
_select_school = _session.select_school


def _download_report_csv(page: Page, report_url: str) -> bytes:
    """Navega até o relatório e baixa o CSV (Gerar relatório -> Gerar Excel -> CSV)."""
    _assert_read_only()
    page.goto(report_url, wait_until="domcontentloaded", timeout=30000)
    _wait_loader(page)
    _raise_if_expired(page)
    try:
        page.wait_for_selector("button:has-text('Gerar relatório')", timeout=10000)
    except Exception:
        pass

    # 1. Gerar relatório
    try:
        page.get_by_role("button", name="Gerar relatório").first.click(timeout=5000)
    except PlaywrightTimeoutError:
        _raise_if_expired(page)
        raise PreenchimentoNaoIniciado()

    # Disputa o desfecho após "Gerar relatório": snackbar de erro
    # ("Nenhum registro encontrado para essa pesquisa.") OU o botão "Gerar Excel".
    snack = page.locator("snack-bar-container:has-text('Nenhum registro encontrado')")
    excel_btn = page.get_by_role("button", name="Gerar Excel")
    _wait_loader(page)
    for _ in range(32):  # ~8s (32 x 250ms)
        if snack.count() > 0:
            raise RelatorioInexistente()
        if excel_btn.count() > 0 and excel_btn.first.is_visible():
            break
        page.wait_for_timeout(250)

    # 2. Gerar Excel (abre o menu com as opções de exportação) — FLUXO ANTIGO
    #    TENTAR PRIMEIRO o novo botão direto "Gerar CSV" (seletor exato informado)
    csv_direto = page.locator('button:has(span.mat-button-wrapper:has-text("Gerar CSV"))').first
    if csv_direto.count() > 0 and csv_direto.is_visible():
        # NOVO FLUXO: botão direto "Gerar CSV" existe
        try:
            with page.expect_download(timeout=60000) as dl_info:
                csv_direto.click(timeout=15000)
        except PlaywrightTimeoutError:
            _raise_if_expired(page)
            raise
        download = dl_info.value
        path = download.path()
        with open(path, "rb") as f:
            return f.read()

    # FALLBACK: fluxo antigo (Gerar Excel -> menuitem CSV)
    try:
        page.get_by_role("button", name="Gerar Excel").first.click(timeout=15000)
    except PlaywrightTimeoutError:
        _raise_if_expired(page)
        raise
    _wait_loader(page)
    try:
        page.wait_for_selector("[role='menuitem']:has-text('CSV')", timeout=5000)
    except Exception:
        pass

    # 3. CSV (item de menu) -> dispara o download
    try:
        with page.expect_download(timeout=60000) as dl_info:
            page.get_by_role("menuitem", name="CSV").first.click(timeout=15000)
    except PlaywrightTimeoutError:
        _raise_if_expired(page)
        raise
    download = dl_info.value
    path = download.path()
    with open(path, "rb") as f:
        return f.read()


_MOTIVO_INTERROMPIDO = _session.MOTIVO_INTERROMPIDO


_marcar_nao_processadas = _session.marcar_nao_processadas


def _pausa_entre_escolas() -> float:
    """Wrapper de `apps.common.coleta` (histórico)."""
    return _coleta.pausa_entre_escolas()


def _log_tempo_escola(codigo: str, t0: float) -> None:
    """Wrapper de `apps.common.coleta` (histórico)."""
    return _coleta.log_tempo_escola(logger, codigo, t0)


def _registrar_sucesso(outputs, on_school_done, escola, dados) -> None:
    """Wrapper de `apps.common.coleta` (histórico)."""
    return _coleta.registrar_sucesso(outputs, on_school_done, escola, dados)


def _mapear_excecao(exc: BaseException) -> tuple[str, str] | None:
    """Motivo/progresso das falhas rotineiras de relatório (baseline 4.3)."""
    if isinstance(exc, PreenchimentoNaoIniciado):
        return ("Preenchimento não iniciado", "Preenchimento não iniciado.")
    if isinstance(exc, RelatorioInexistente):
        return ("Relatório inexistente", "Relatório inexistente.")
    return None


_TEXTOS = _coleta.TextosColeta(
    log_abort="Falha no login inicial. Abortando coleta de relatórios.",
    log_inicio_loop="Login realizado com sucesso. Iniciando loop de relatórios.",
    formatar_log_erro=lambda codigo, exc: f"[{codigo}] Erro durante a coleta de relatório: {exc}",
    formatar_motivo_relogin=lambda exc: str(exc),
    mapear_excecao=_mapear_excecao,
)


def run_report_scraping(
    browser: Browser,
    login: str,
    senha: str,
    escolas: list[dict],
    report_url: str,
    on_progress=None,
    stop_check=None,
    on_school_done=None,
) -> tuple[list[tuple[dict, bytes]], list[dict]]:
    """Wrapper de `apps.common.coleta` (histórico): coleta dos relatórios (CSV)."""

    def _scrape_one(context, page, codigo: str, nome: str):
        if not _select_school(page, codigo):
            return None
        return _download_report_csv(page, report_url)

    return _coleta.run_coleta(
        browser,
        login,
        senha,
        escolas,
        scrape_one=_scrape_one,
        hooks=_coleta.ColetaHooks(
            login_and_read=_login_and_read,
            session_expirada=_session_expirada,
            safe_cleanup=_safe_cleanup,
            pausa_entre_escolas=_pausa_entre_escolas,
            log_tempo_escola=_log_tempo_escola,
            registrar_sucesso=_registrar_sucesso,
            marcar_nao_processadas=_marcar_nao_processadas,
        ),
        textos=_TEXTOS,
        logger=logger,
        accept_downloads=True,
        on_progress=on_progress,
        stop_check=stop_check,
        on_school_done=on_school_done,
    )
