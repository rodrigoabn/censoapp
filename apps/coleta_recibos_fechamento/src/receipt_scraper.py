"""Coleta de recibos de fechamento do Educacenso em MODO LEITURA (Playwright).

Fluxo por escola (apenas leitura/navegação):
  1. Login via Keycloak (acesso.inep.gov.br) com CPF + senha.
  2. Seleção da escola em /escola/pesquisar pelo código Inep (aceita o Termo
     de Sigilo se exibido — necessário apenas para acessar/navegar).
  3. Navega até a tela de fechamento (/fechamento).
  4. Loop dentro do contexto: procura o link do recibo ("Recibo" / "Clique
     aqui para visualizar, salvar ou imprimir o recibo").
       - Se NÃO existir após N tentativas -> escola pulada (ReciboIndisponivel).
       - Se existir -> clica. O site dispara o download de um PDF (blob:).
  5. Captura o download e retorna os bytes do PDF.

NUNCA preenche, marca ou submete dados de questionário no site. A única saída
é o recibo (PDF) que o próprio Educacenso disponibiliza.
"""

from __future__ import annotations

import logging

from playwright.sync_api import Browser, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from apps.common import browser as _browser
from apps.common import coleta as _coleta
from apps.common import session as _session

from .auth import _assert_read_only

logger = logging.getLogger("coleta_recibos_fechamento")


class ReciboIndisponivel(Exception):
    """Sinaliza que o recibo de fechamento não pôde ser baixado porque o link
    do recibo não ficou disponível para a escola (fechamento não concluído
    ou tela indisponível)."""


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


def _find_recibo_link(page: Page):
    """Localiza o link do recibo na tela de fechamento, se presente/visível.

    Na escola fechada o site exibe o link "Clique aqui para visualizar, salvar
    ou imprimir o recibo" (texto do botão/aba "Recibo"). O clique dispara o
    download do PDF do recibo. Retorna o locator clicável ou None.
    """
    seletores = (
        "a:has-text('Clique aqui')",
        "a:has-text('Recibo')",
        "button:has-text('Recibo')",
    )
    for sel in seletores:
        loc = page.locator(sel).first
        try:
            if loc.count() and loc.is_visible():
                return loc
        except Exception:
            continue
    return None


def _download_receipt_pdf(context, page: Page, receipt_url: str) -> bytes:
    """Navega até a tela de fechamento e baixa o recibo (PDF).

    Aguarda o link do recibo aparecer na tela (espera única) e, ao existir,
    clica; o site dispara o download de um PDF (blob:). Captura o download e
    retorna os bytes. Levanta ReciboIndisponivel se o link não aparecer ou se
    o conteúdo baixado não for um PDF válido.
    """
    _assert_read_only()
    page.goto(receipt_url, wait_until="domcontentloaded", timeout=30000)
    _wait_loader(page)
    _raise_if_expired(page)

    # ── Espera única: o link do recibo aparece assim que a tela carrega ─────
    try:
        page.wait_for_selector(
            "a:has-text('Clique aqui'), a:has-text('Recibo'), button:has-text('Recibo')",
            state="visible",
            timeout=15000,
        )
    except Exception:
        _raise_if_expired(page)
        raise ReciboIndisponivel()

    link = _find_recibo_link(page)
    if link is None:
        _raise_if_expired(page)
        raise ReciboIndisponivel()

    # ── Clica no link e captura o download do PDF ───────────────────────────
    try:
        with page.expect_download(timeout=30000) as dl_info:
            link.click(timeout=10000)
        download = dl_info.value
        with open(download.path(), "rb") as f:
            data = f.read()
    except PlaywrightTimeoutError:
        _raise_if_expired(page)
        raise ReciboIndisponivel()

    if not data or data[:4] != b"%PDF":
        raise ReciboIndisponivel()
    return data


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
    """Motivo/progresso das falhas rotineiras de recibo (baseline 4.3)."""
    if isinstance(exc, ReciboIndisponivel):
        return ("Recibo de fechamento indisponível", "Recibo de fechamento indisponível.")
    return None


_TEXTOS = _coleta.TextosColeta(
    log_abort="Falha no login inicial. Abortando coleta de recibos.",
    log_inicio_loop="Login realizado com sucesso. Iniciando loop de recibos.",
    formatar_log_erro=lambda codigo, exc: f"[{codigo}] Erro durante a coleta do recibo: {exc}",
    formatar_motivo_relogin=lambda exc: str(exc),
    mapear_excecao=_mapear_excecao,
)


def run_receipt_scraping(
    browser: Browser,
    login: str,
    senha: str,
    escolas: list[dict],
    receipt_url: str,
    on_progress=None,
    stop_check=None,
    on_school_done=None,
) -> tuple[list[tuple[dict, bytes]], list[dict]]:
    """Wrapper de `apps.common.coleta` (histórico): coleta dos recibos (PDF)."""

    def _scrape_one(context, page, codigo: str, nome: str):
        if not _select_school(page, codigo):
            return None
        return _download_receipt_pdf(context, page, receipt_url)

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
