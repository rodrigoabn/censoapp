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
import os
import time

from playwright.sync_api import Browser, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from apps.common import browser as _browser
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
    """Pausa entre escolas (CENSO_SLEEP_ESCOLAS; default 0.3s)."""
    try:
        pausa = float(os.environ.get("CENSO_SLEEP_ESCOLAS", "0.3"))
    except ValueError:
        return 0.3
    if not (0 <= pausa < float("inf")):
        return 0.3
    return pausa


def _log_tempo_escola(codigo: str, t0: float) -> None:
    """Loga o tempo decorrido de processamento de uma escola (em segundos)."""
    logger.info(f"[{codigo}] escola processada em {time.monotonic() - t0:.1f}s")


def _registrar_sucesso(outputs, on_school_done, escola, dados) -> None:
    """Grava incrementalmente (se houver callback) e acumula para o retorno.

    O callback roda ANTES do append: se a gravação falhar, a exceção vira
    falha da escola (entra em 'não coletadas') — nada some em silêncio.
    """
    if on_school_done is not None:
        on_school_done(escola, dados)
    outputs.append((escola, dados))


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
    """Varre a lista de escolas em loop, com sessão única reutilizada.

    Fluxo: login uma única vez (Keycloak) → loop de escolas (navega e seleciona
    a escola via /escola/pesquisar) → baixa o recibo de fechamento (PDF) de cada
    uma. Re-loga automaticamente apenas se a sessão Keycloak expirar.
    """
    _assert_read_only()
    t_inicio = time.monotonic()
    outputs: list[tuple[dict, bytes]] = []
    failures: list[dict] = []

    # ── Login inicial ──────────────────────────────────────────────────────
    context = browser.new_context(accept_downloads=True)
    page = context.new_page()
    logged_in = False
    for _attempt in range(2):
        try:
            _login_and_read(page, login, senha)
            logged_in = True
            break
        except LoginFalhou:
            time.sleep(1)
            continue
        except Exception:
            break

    if not logged_in:
        logger.error("Falha no login inicial. Abortando coleta de recibos.")
        failures.extend(
            {
                "codigo_inep": e["codigo_inep"],
                "nome_unidade": e.get("nome_unidade", ""),
                "motivo": "Falha no login",
            }
            for e in escolas
        )
        _safe_cleanup(context, page)
        return outputs, failures

    logger.info("Login realizado com sucesso. Iniciando loop de recibos.")

    # ── Loop de escolas (sessão reutilizada) ───────────────────────────────
    for i, escola in enumerate(escolas, 1):
        codigo = escola["codigo_inep"]
        nome = escola.get("nome_unidade", "")
        t0 = time.monotonic()

        if stop_check and stop_check():
            _marcar_nao_processadas(failures, escolas[i - 1:])
            break
        if on_progress:
            on_progress(i - 1, len(escolas), codigo, nome, "Coletando dados ...")

        # Verifica se a sessão ainda está ativa antes de cada escola.
        if _session_expirada(page):
            logger.warning(f"[{codigo}] Sessão expirada. Realizando re-login...")
            try:
                _login_and_read(page, login, senha)
                logger.info(f"[{codigo}] Re-login concluído.")
            except Exception as exc:
                failures.append({"codigo_inep": codigo, "nome_unidade": nome, "motivo": f"Erro (re-login): {exc}"})
                if on_progress:
                    on_progress(i, len(escolas), codigo, nome, f"erro: sessão expirada — {exc}")
                _log_tempo_escola(codigo, t0)
                continue

        try:
            if not _select_school(page, codigo):
                failures.append({"codigo_inep": codigo, "nome_unidade": nome,
                                 "motivo": "Escola não encontrada"})
                if on_progress:
                    on_progress(i, len(escolas), codigo, nome, "erro: escola não encontrada")
                continue

            data = _download_receipt_pdf(context, page, receipt_url)

            if stop_check and stop_check():
                if on_progress:
                    on_progress(i, len(escolas), codigo, nome, "interrompido")
                _marcar_nao_processadas(failures, escolas[i - 1:])
                break

            _registrar_sucesso(outputs, on_school_done, escola, data)
            if on_progress:
                on_progress(i, len(escolas), codigo, nome, "concluído")

        except ReciboIndisponivel:
            failures.append({"codigo_inep": codigo, "nome_unidade": nome,
                             "motivo": "Recibo de fechamento indisponível"})
            if on_progress:
                on_progress(i, len(escolas), codigo, nome, "Recibo de fechamento indisponível.")

        except SessaoExpirada:
            # Sessão caiu ao abrir a ficha. Re-loga e repete a mesma escola.
            logger.warning(f"[{codigo}] Sessão expirada ao abrir a ficha. Re-logando e repetindo...")
            try:
                _login_and_read(page, login, senha)
                if not _select_school(page, codigo):
                    raise ReciboIndisponivel()
                data = _download_receipt_pdf(context, page, receipt_url)
                _registrar_sucesso(outputs, on_school_done, escola, data)
                if on_progress:
                    on_progress(i, len(escolas), codigo, nome, "concluído")
            except Exception as exc2:  # noqa: BLE001
                logger.error(f"[{codigo}] Falha após re-login: {exc2}")
                failures.append({"codigo_inep": codigo, "nome_unidade": nome,
                                 "motivo": f"Erro (após re-login): {exc2}"})
                if on_progress:
                    on_progress(i, len(escolas), codigo, nome, f"erro: {exc2}")

        except Exception as exc:  # noqa: BLE001
            logger.error(f"[{codigo}] Erro durante a coleta do recibo: {exc}")
            failures.append({"codigo_inep": codigo, "nome_unidade": nome,
                             "motivo": f"Erro: {exc}"})
            if on_progress:
                on_progress(i, len(escolas), codigo, nome, f"erro: {exc}")
        finally:
            _log_tempo_escola(codigo, t0)

        # Pequena pausa entre escolas
        time.sleep(_pausa_entre_escolas())

    # ── Encerra a sessão única ao final ───────────────────────────────────
    _safe_cleanup(context, page)
    tempo_total = time.monotonic() - t_inicio
    logger.info(
        f"Coleta concluída: {len(outputs)} escola(s) coletada(s), {len(failures)} falha(s), "
        f"{tempo_total:.1f}s no total ({tempo_total / max(1, len(escolas)):.1f}s por escola em média). "
        "Sessão encerrada."
    )
    return outputs, failures
