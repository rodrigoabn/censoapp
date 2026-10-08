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

import time
import logging

from playwright.sync_api import Browser, Page, TimeoutError as PlaywrightTimeoutError

from .auth import BASE_URL, READ_ONLY

logger = logging.getLogger("coleta_relatorios")


class PreenchimentoNaoIniciado(Exception):
    """Sinaliza que o relatório não pôde ser gerado porque a escola ainda não
    iniciou o preenchimento (botão 'Gerar relatório' indisponível)."""


class RelatorioInexistente(Exception):
    """Relatório não gerado: o site exibiu a snackbar de erro
    'Nenhum registro encontrado para essa pesquisa.' após 'Gerar relatório'."""


class LoginFalhou(Exception):
    """Login não concluído (instabilidade): o botão '#kc-login' não habilitou
    e o formulário de login continuou visível após a tentativa."""


class SessaoExpirada(Exception):
    """A sessão Keycloak expirou (ou a navegação caiu na tela de login) durante
    a abertura da ficha. O chamador deve refazer o login e repetir."""


def _assert_read_only() -> None:
    if not READ_ONLY:
        raise RuntimeError("MODO LEITURA violado: escrita no site proibida.")


def _safe_cleanup(context, page) -> None:
    """Fecha página/contexto com segurança (ignora erros e valores None)."""
    try:
        if context is not None:
            context.clear_cookies()
    except Exception:
        pass
    try:
        if page is not None:
            page.close()
    except Exception:
        pass
    try:
        if context is not None:
            context.close()
    except Exception:
        pass


def _wait_loader(page: Page, timeout: int = 6000) -> None:
    """Aguarda o overlay de carregamento (ngx-ui-loader) desaparecer."""
    try:
        page.wait_for_selector("ngx-ui-loader .ngx-overlay", state="hidden", timeout=timeout)
    except Exception:
        pass


def _session_expirada(page: Page) -> bool:
    """Detecta se a sessão Keycloak expirou (página de login voltou)."""
    try:
        return page.locator("input#username").is_visible()
    except Exception:
        return False


def _login_and_read(page: Page, login: str, senha: str) -> None:
    _assert_read_only()
    page.goto(f"{BASE_URL}/escola/pesquisar", wait_until="domcontentloaded", timeout=30000)
    _wait_loader(page)
    page.wait_for_selector("input#username", state="visible", timeout=10000)

    user = page.locator("input#username")
    pwd = page.locator("input#password")
    user.click()
    user.fill(login)
    pwd.click()
    pwd.fill(senha)
    # Dispara a validação (blur) para habilitar o botão de login.
    pwd.press("Tab")

    # Aguarda o botão habilitar; se não habilitar, submete pelo Enter (fallback).
    try:
        page.wait_for_selector("#kc-login:not([disabled])", timeout=8000)
        page.locator("#kc-login").click(timeout=5000)
    except PlaywrightTimeoutError:
        pwd.press("Enter")

    page.wait_for_timeout(4000)

    # Verifica se o login foi concluído (formulário não deve mais estar visível).
    if page.locator("input#username").is_visible():
        raise LoginFalhou()


def _accept_sigilo_if_present(page: Page) -> None:
    """Aceita o Termo de Sigilo, se exibido (modo leitura/navegação).

    O termo só habilita o checkbox após rolar o texto até o final. Marcar o
    aceite e clicar 'Continuar' é necessário para ACESSAR a escola (leitura),
    não altera nenhum dado.
    """
    _assert_read_only()
    try:
        page.wait_for_selector("mat-dialog-container", timeout=8000)
    except Exception:
        return
    for _ in range(30):
        page.evaluate(
            "() => { const m = document.querySelector('mat-dialog-container .modal-body');"
            " if (m) m.scrollTop = m.scrollHeight; }"
        )
        page.wait_for_timeout(200)
        cb = page.locator("mat-dialog-container input[type='checkbox']").first
        if cb.count() and not cb.is_disabled():
            break
    cb = page.locator("mat-dialog-container input[type='checkbox']").first
    if cb.count() and not cb.is_disabled():
        cb.check(force=True)
    continuar = page.locator("button:has-text('Continuar')").first
    if continuar.count() and continuar.is_enabled():
        continuar.click()
    page.wait_for_timeout(3000)


def _select_school(page: Page, codigo_inep: str, tentativas: int = 3) -> bool:
    """Busca a escola pelo código e a seleciona (contexto de sessão).

    Robusto contra o loader travar (retry de navegação) e contra a sessão
    expirar no meio do caminho (levanta `SessaoExpirada`)."""
    _assert_read_only()
    last_exc: Exception | None = None
    for _ in range(max(1, tentativas)):
        try:
            page.goto(f"{BASE_URL}/escola/pesquisar", wait_until="domcontentloaded", timeout=15000)
            _wait_loader(page)
            if _session_expirada(page):
                raise SessaoExpirada()
            page.wait_for_selector("input[formcontrolname='codigoEscola']", timeout=15000)
            break
        except SessaoExpirada:
            raise
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            page.wait_for_timeout(1000)
            continue
    else:
        if last_exc is not None:
            raise last_exc

    page.fill("input[formcontrolname='codigoEscola']", codigo_inep)
    btn = page.locator("button:has-text('Pesquisar')").first
    if btn.count():
        btn.click()
    
    try:
        page.wait_for_selector(
            f"a.cursor-pointer:has-text('{codigo_inep}'), h5:has-text('encontrado')",
            timeout=10000,
        )
    except Exception:
        pass
    _wait_loader(page)

    link = page.locator(f"a.cursor-pointer:has-text('{codigo_inep}')").first
    if not link.count():
        return False
    link.click()
    _wait_loader(page)
    try:
        page.wait_for_selector("mat-dialog-container, button:has-text('Gerar')", timeout=10000)
    except Exception:
        pass

    _accept_sigilo_if_present(page)
    return True


def _download_report_csv(page: Page, report_url: str) -> bytes:
    """Navega até o relatório e baixa o CSV (Gerar relatório -> Gerar Excel -> CSV)."""
    _assert_read_only()
    page.goto(report_url, wait_until="domcontentloaded", timeout=30000)
    _wait_loader(page)
    try:
        page.wait_for_selector("button:has-text('Gerar relatório')", timeout=10000)
    except Exception:
        pass

    # 1. Gerar relatório
    try:
        page.get_by_role("button", name="Gerar relatório").first.click(timeout=5000)
    except PlaywrightTimeoutError:
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
        with page.expect_download(timeout=60000) as dl_info:
            csv_direto.click(timeout=15000)
        download = dl_info.value
        path = download.path()
        with open(path, "rb") as f:
            return f.read()

    # FALLBACK: fluxo antigo (Gerar Excel -> menuitem CSV)
    page.get_by_role("button", name="Gerar Excel").first.click(timeout=15000)
    _wait_loader(page)
    try:
        page.wait_for_selector("[role='menuitem']:has-text('CSV')", timeout=5000)
    except Exception:
        pass

    # 3. CSV (item de menu) -> dispara o download
    with page.expect_download(timeout=60000) as dl_info:
        page.get_by_role("menuitem", name="CSV").first.click(timeout=15000)
    download = dl_info.value
    path = download.path()
    with open(path, "rb") as f:
        return f.read()


def run_report_scraping(
    browser: Browser,
    login: str,
    senha: str,
    escolas: list[dict],
    report_url: str,
    on_progress=None,
    stop_check=None,
) -> tuple[list[tuple[dict, bytes]], list[dict]]:
    """Varre a lista de escolas em loop, com sessão única reutilizada.

    Fluxo: login uma única vez (Keycloak) → loop de escolas (navega e seleciona
    a escola via /escola/pesquisar) → baixa o CSV do relatório de cada uma.
    Re-loga automaticamente apenas se a sessão Keycloak expirar.
    """
    _assert_read_only()
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
        _safe_cleanup(context, page)
        return outputs, failures

    logger.info("Login realizado com sucesso. Iniciando loop de relatórios.")

    # ── Loop de escolas (sessão reutilizada) ───────────────────────────────
    for i, escola in enumerate(escolas, 1):
        codigo = escola["codigo_inep"]
        nome = escola.get("nome_unidade", "")

        if stop_check and stop_check():
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
                break

            outputs.append((escola, data))
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
                outputs.append((escola, data))
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

        # Pequena pausa entre escolas
        time.sleep(0.3)

    # ── Encerra a sessão única ao final ───────────────────────────────────
    _safe_cleanup(context, page)
    logger.info("Coleta de relatórios concluída. Sessão encerrada.")
    return outputs, failures
