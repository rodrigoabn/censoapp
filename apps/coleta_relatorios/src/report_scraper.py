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
import os
import time

from playwright.sync_api import Browser, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from apps.common import browser as _browser
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
    """Varre a lista de escolas em loop, com sessão única reutilizada.

    Fluxo: login uma única vez (Keycloak) → loop de escolas (navega e seleciona
    a escola via /escola/pesquisar) → baixa o CSV do relatório de cada uma.
    Re-loga automaticamente apenas se a sessão Keycloak expirar.
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
        logger.error("Falha no login inicial. Abortando coleta de relatórios.")
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

    logger.info("Login realizado com sucesso. Iniciando loop de relatórios.")

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

            data = _download_report_csv(page, report_url)

            if stop_check and stop_check():
                if on_progress:
                    on_progress(i, len(escolas), codigo, nome, "interrompido")
                _marcar_nao_processadas(failures, escolas[i - 1:])
                break

            _registrar_sucesso(outputs, on_school_done, escola, data)
            if on_progress:
                on_progress(i, len(escolas), codigo, nome, "concluído")

        except PreenchimentoNaoIniciado:
            failures.append({"codigo_inep": codigo, "nome_unidade": nome,
                             "motivo": "Preenchimento não iniciado"})
            if on_progress:
                on_progress(i, len(escolas), codigo, nome, "Preenchimento não iniciado.")

        except RelatorioInexistente:
            failures.append({"codigo_inep": codigo, "nome_unidade": nome,
                             "motivo": "Relatório inexistente"})
            if on_progress:
                on_progress(i, len(escolas), codigo, nome, "Relatório inexistente.")

        except SessaoExpirada:
            # Sessão caiu ao abrir a ficha. Re-loga e repete a mesma escola.
            logger.warning(f"[{codigo}] Sessão expirada ao abrir a ficha. Re-logando e repetindo...")
            try:
                _login_and_read(page, login, senha)
                if not _select_school(page, codigo):
                    raise RelatorioInexistente()
                data = _download_report_csv(page, report_url)
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
            logger.error(f"[{codigo}] Erro durante a coleta de relatório: {exc}")
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
