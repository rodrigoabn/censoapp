"""Scraper do Gestor Escolar no Educacenso em MODO LEITURA (Playwright).

Fluxo calibrado (apenas leitura):
   1. Login via Keycloak (acesso.inep.gov.br) com CPF + senha.         [reutilizado]
   2. Busca e seleção da escola em /escola/pesquisar.                   [reutilizado]
   3. Navegação para /gestor/pesquisar.
   4. Seleção do filtro "Apenas na escola" + clique em "Pesquisar".
   5. Verificação de registros ("Foi encontrado N registro(s)").
   6. Abertura do vínculo (ícone "list" -> ícone "editing").
   7. Aceite do Termo de Sigilo, se exibido.
   8. Extração dos campos do gestor (Cargo, Critério, Situação, Email).

NUNCA preenche, marca ou submete dados de questionário no site. A única
escrita permitida é no XLSX de saída (exporter.py).
"""

from __future__ import annotations

import re
import time
import logging

from playwright.sync_api import Browser, Page, TimeoutError as PlaywrightTimeoutError

from . import modelo
from .auth import BASE_URL, READ_ONLY, _assert_read_only

logger = logging.getLogger("coleta_gestor")

SHEET = modelo.GESTOR_SHEET

# Script de extração executado no browser (apenas leitura do DOM).
# Captura mat-form-field (selects/inputs), mat-checkbox e mat-radio-button,
# mapeando rótulos -> valores.
_EXTRACT_JS = """() => {
  const out = [];
  const seen = new Set();
  const push = (label, value) => {
    if (!label) return;
    label = label.trim();
    if (!label || seen.has(label)) return;
    seen.add(label);
    out.push({ label: label, value: (value || '').toString().trim() });
  };
  document.querySelectorAll('mat-form-field').forEach(ff => {
    const sel = ff.querySelector('mat-select');
    let label = (sel && (sel.getAttribute('aria-label') || sel.getAttribute('placeholder')))
             || (ff.querySelector('input') && ff.querySelector('input').getAttribute('placeholder'));
    if (!label) {
      let node = ff;
      for (let i = 0; i < 4 && !label; i++) {
        node = node.parentElement;
        if (!node) break;
        const spans = node.parentElement ? node.parentElement.querySelectorAll('span') : [];
        for (const s of spans) {
          const t = s.innerText.trim();
          if (t && t.length > 5 && !/^\\d+$/.test(t)) { label = t; break; }
        }
      }
    }
    let value = '';
    const sv = ff.querySelector('.mat-select-value-text');
    if (sv) value = sv.innerText.trim();
    else {
      const inp = ff.querySelector('input');
      if (inp) value = (inp.value || inp.innerText || '').trim();
    }
    push(label, value);
  });
  document.querySelectorAll('mat-checkbox').forEach(cb => {
    const lbl = cb.querySelector('.mat-checkbox-label');
    const label = lbl ? lbl.innerText.trim() : (cb.getAttribute('aria-label') || '');
    const checked = cb.querySelector('input') && cb.querySelector('input').checked;
    push(label, checked ? 'Sim' : '');
  });
  document.querySelectorAll('mat-radio-button').forEach(rb => {
    const lbl = rb.querySelector('.mat-radio-label-content, .mdc-label, label');
    const label = lbl ? lbl.innerText.trim() : (rb.getAttribute('aria-label') || '');
    const inp = rb.querySelector('input[type="radio"]');
    const checked = (inp && inp.checked)
        || rb.classList.contains('mat-radio-checked')
        || rb.classList.contains('mat-mdc-radio-checked');
    push(label, checked ? 'Sim' : '');
  });
  return out;
}"""


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


def _wait_loader(page: Page, timeout: int = 15000) -> None:
    """Aguarda o overlay de carregamento (ngx-ui-loader) desaparecer."""
    try:
        page.wait_for_selector("ngx-ui-loader .ngx-overlay", state="hidden", timeout=timeout)
    except Exception:
        pass
    try:
        page.wait_for_selector("mat-spinner, .mat-progress-spinner", state="hidden", timeout=3000)
    except Exception:
        pass


def _wait_content_ready(page: Page, min_fields: int = 1, timeout: int = 15000) -> bool:
    """Aguarda que ao menos `min_fields` mat-form-fields estejam
    renderizados na página (indica que o Angular terminou de carregar
    os dados do formulário).

    Retorna True se os campos foram detectados, False caso contrário.
    """
    try:
        page.wait_for_selector("mat-form-field", state="visible", timeout=timeout)
    except Exception:
        return False

    # Polling: verifica se os campos têm conteúdo (não estão vazios).
    deadline = time.monotonic() + (timeout / 1000)
    while time.monotonic() < deadline:
        count = page.evaluate("""() => {
            const fields = document.querySelectorAll('mat-form-field');
            let filled = 0;
            fields.forEach(ff => {
                const sv = ff.querySelector('.mat-select-value-text');
                const inp = ff.querySelector('input');
                if ((sv && sv.innerText.trim()) || (inp && (inp.value || '').trim())) {
                    filled++;
                }
            });
            return filled;
        }""")
        if count >= min_fields:
            return True
        page.wait_for_timeout(300)
    return False


class LoginFalhou(Exception):
    """Login não concluído (instabilidade): o botão '#kc-login' não habilitou
    e o formulário de login continuou visível após a tentativa."""


class SessaoExpirada(Exception):
    """A sessão Keycloak expirou (ou a navegação caiu na tela de login) durante
    a abertura da ficha. O chamador deve refazer o login e repetir."""


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
    aceite e clicar 'Continuar' é necessário para ACESSAR os dados (leitura),
    não altera nenhum dado da escola.
    """
    _assert_read_only()
    try:
        page.wait_for_selector("mat-dialog-container", timeout=8000)
    except Exception:
        return  # diálogo não apareceu (termo já aceito anteriormente)
    # Rola o corpo do termo até o fim para habilitar o checkbox.
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
    continuar = page.locator("mat-dialog-container button:has-text('Continuar')").first
    if continuar.count() and continuar.is_enabled():
        continuar.click()
    page.wait_for_timeout(3000)

def _is_escola_fechada(page: Page) -> bool:
    """Detecta se a escola está com o sistema de retificação fechado
    (exibe o cartão de aviso 'Escola Fechada!' no portal)."""
    try:
        return page.locator(".warning-card:has-text('Escola Fechada')").count() > 0
    except Exception:
        return False


def _open_school_ficha(page: Page, codigo_inep: str, tentativas: int = 3) -> bool:
    """Busca a escola pelo código e abre a ficha (leitura). Reutiliza o fluxo
    do coleta_cadastros_escolas para fixar o contexto da escola na sessão.

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
    
    # Espera pelo resultado da pesquisa (link com o código ou mensagem de sem registros).
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
        page.wait_for_selector("mat-dialog-container, li.tab-item, mat-form-field", timeout=10000)
    except Exception:
        pass

    # Diálogo de Termo de Sigilo (se houver) — apenas aceite para navegar.
    _accept_sigilo_if_present(page)

    if "/escola/cadastro/dados-cadastrais" not in page.url:
        try:
            page.goto(f"{BASE_URL}/escola/cadastro/dados-cadastrais", wait_until="domcontentloaded", timeout=15000)
            _wait_loader(page)
        except Exception:
            pass
    else:
        _wait_loader(page)

    try:
        page.wait_for_selector("li.tab-item, mat-form-field", timeout=10000)
    except Exception:
        pass
    return True


def _map_to_row(fields: list[dict], cols: list[str]) -> dict:
    """Mapeia os campos extraídos para as colunas do modelo (gestor).

    Estratégias (nesta ordem): alias explícito, igualdade exata normalizada,
    substring bidirecional (>=6 chars).
    """
    norm_map = {modelo._normalize(c): c for c in cols}
    row: dict = {c: "" for c in cols}
    for f in fields:
        key = modelo._normalize(f["label"])
        if not key:
            continue
        # 1. Alias explícito
        alias = modelo.resolve_field_label(key)
        if alias and alias in cols:
            row[alias] = f["value"]
            continue
        # 2. Igualdade exata
        if key in norm_map:
            row[norm_map[key]] = f["value"]
            continue
        # 3. Substring (bidirecional, com comprimento mínimo).
        # Proteção contra falso positivo: evita que rótulos CURTOS (do site ou
        # do modelo) cassem incidentalmente com rótulos LONGOs onde estão
        # "escondidos" no meio. Ex.: "federal"/"estadual"/"municipal" (curtos)
        # não devem sobrescrever o atributo "2 - Regulamentação/autorização...
        # no conselho ou órgão municipal, estadual ou federal de educação".
        for colnorm, col in norm_map.items():
            if len(colnorm) < 6 or len(key) < 6:
                continue
            # Modelo contido no site: só se o rótulo do modelo for
            # razoavelmente longo (não uma palavra curta solta).
            if colnorm in key and len(colnorm) >= 10:
                row[col] = f["value"]
                break
            # Site contido no modelo: só se o rótulo do site for
            # razoavelmente longo (não uma palavra curta solta).
            if key in colnorm and len(key) >= 10:
                row[col] = f["value"]
                break
    return row


def _registros_encontrados(page: Page) -> int:
    """Lê o número de registros encontrados ('Foi encontrado N registro(s)')."""
    h5 = page.locator("h5:has-text('Foi encontrado')").first
    if not h5.count():
        return -1
    try:
        texto = h5.inner_text()
    except Exception:
        return -1
    m = re.search(r"(\d+)", texto)
    return int(m.group(1)) if m else -1


def _fechar_ou_cancelar_gestor(page: Page) -> None:
    """Fecha o modal/drawer do gestor (modo leitura) clicando em 'Cancelar' ou
    'Fechar', conforme o contexto da tela. Nunca clica em 'Salvar'.

    Tenta 'Cancelar' primeiro; se não estiver presente/clicável, tenta
    'Fechar'. Ignora silenciosamente se nenhum existir.
    """
    page.wait_for_timeout(500)
    for texto in ("Cancelar", "Fechar"):
        btn = page.locator(f"button:has-text('{texto}')").first
        if btn.count() and btn.is_visible():
            try:
                btn.click(timeout=5000)
                page.wait_for_timeout(500)
                return
            except Exception:
                return


def _abrir_pesquisa_gestor(page: Page) -> int:
    """Navega para /gestor/pesquisar, marca 'Apenas na escola', clica
    'Pesquisar' e devolve o número de registros encontrados (-1 se incerto)."""
    page.goto(f"{BASE_URL}/gestor/pesquisar", wait_until="domcontentloaded", timeout=30000)
    _wait_loader(page)
    try:
        page.wait_for_selector("label.mat-radio-label, button:has-text('Pesquisar')", timeout=15000)
    except Exception:
        pass

    # Selecionar o filtro "Apenas na escola".
    radio = page.locator("label.mat-radio-label:has-text('Apenas na escola')").first
    if radio.count():
        radio.click()
    page.wait_for_timeout(300)

    # Clicar em "Pesquisar".
    pesquisar = page.locator("button:has-text('Pesquisar')").first
    if pesquisar.count():
        pesquisar.click()
    _wait_loader(page)
    try:
        page.wait_for_selector("h5:has-text('encontrado'), mat-icon:has-text('list')", timeout=15000)
    except Exception:
        pass

    return _registros_encontrados(page)


def _extract_with_retry(page: Page, cols: list[str], max_retries: int = 2) -> list[dict]:
    """Executa _EXTRACT_JS com retry se poucos campos forem extraídos.

    Se a primeira tentativa retorna menos de 30% das colunas esperadas,
    espera mais tempo e tenta novamente (o Angular pode não ter terminado
    de renderizar os dados).
    """
    min_expected = max(1, len(cols) // 3)
    for attempt in range(max_retries + 1):
        try:
            fields = page.evaluate(_EXTRACT_JS)
        except Exception:
            fields = []

        if len(fields) >= min_expected:
            return fields

        if attempt < max_retries:
            page.wait_for_timeout((attempt + 1) * 2000)
            _wait_content_ready(page, min_fields=1, timeout=5000)

    return fields


def _scrape_gestor_vinculo(page: Page, codigo_inep: str, nome_unidade: str) -> dict:
    """Fase A — coleta a aba 'Vínculo do gestor' via list -> vincular."""
    _assert_read_only()
    model = modelo.load_model()
    cols = model.get(modelo.GESTOR_SHEET, [])
    row: dict = {c: "" for c in cols}
    row["Código do Inep"] = codigo_inep
    row["Unidade Escolar"] = nome_unidade

    n = _abrir_pesquisa_gestor(page)
    if n == 0:
        return row

    # Abrir o vínculo (ícone "list").
    list_icon = page.locator("mat-icon:has-text('list')").first
    if list_icon.count():
        logger.info(f"[{codigo_inep}] Botão 'list' encontrado — abrindo vínculo do gestor.")
        list_icon.click(force=True)
    else:
        logger.warning(f"[{codigo_inep}] Botão 'list' NÃO encontrado na lista de vínculos.")
        return row
    _wait_loader(page)

    if _is_escola_fechada(page):
        logger.warning(f"[{codigo_inep}] Escola Fechada detectada — vínculo pode estar em modo somente visualização.")

    # No modal, clicar no ícone "visibility" (último = o dentro do modal).
    # O primeiro visibility é da página de resultados; o último é o da tabela do modal.
    vis_count = page.locator("mat-icon:has-text('visibility')").count()
    if vis_count > 1:
        vis_modal = page.locator("mat-icon:has-text('visibility')").nth(vis_count - 1)
        logger.info(f"[{codigo_inep}] Ícone 'visibility' no modal encontrado — navegando para vínculo.")
        vis_modal.click(force=True)
    elif vis_count == 1:
        logger.warning(f"[{codigo_inep}] Apenas um 'visibility' encontrado (pode ser o da página).")
        return row
    else:
        logger.warning(f"[{codigo_inep}] Nenhum 'visibility' encontrado no modal.")
        return row

    _wait_loader(page)
    try:
        page.wait_for_selector("mat-form-field", timeout=20000)
    except Exception:
        pass

    _accept_sigilo_if_present(page)
    _wait_content_ready(page, min_fields=1, timeout=15000)

    fields = _extract_with_retry(page, cols)
    mapped = _map_to_row(fields, cols)
    mapped["Código do Inep"] = codigo_inep
    mapped["Unidade Escolar"] = nome_unidade

    preenchidos = sum(1 for c, v in mapped.items() if v and c not in modelo.KEY_COLUMNS)
    tot_cols = len([c for c in cols if c not in modelo.KEY_COLUMNS])
    logger.info(f"[{codigo_inep}] Vínculo: coletados {preenchidos}/{tot_cols} campos.")

    try:
        _fechar_ou_cancelar_gestor(page)
    except Exception:
        pass
    return mapped


def _scrape_gestor_edit_form(page: Page, codigo_inep: str, nome_unidade: str) -> dict[str, dict]:
    """Fase B — abre o formulário de cadastro do gestor (ícone 'edit') e coleta
    as abas 'Identificação' e 'Dados pessoais' (e quaisquer outras abas
    existentes no formulário), espelhando o padrão do coleta_cadastros_escolas.

    Retorna {nome_da_aba: {coluna: valor}}. Não altera nenhum dado (modo
    leitura). Ao final, clica em 'Cancelar' para fechar o formulário.
    """
    _assert_read_only()
    model = modelo.load_model()
    result: dict[str, dict] = {}

    n = _abrir_pesquisa_gestor(page)
    if n == 0:
        return result

    # Abrir o cadastro do gestor (ícone "edit" ou "visibility").
    edit_icon = page.locator("mat-icon[mattooltip*='dados cadastrais']").first
    if not edit_icon.count():
        edit_icon = page.locator("mat-icon[mattooltip*='editar os dados cadastrais']").first
    if not edit_icon.count():
        edit_icon = page.locator("mat-icon[mattooltip*='visualizar os dados cadastrais']").first
    if not edit_icon.count():
        edit_icon = page.locator("mat-icon:has-text('edit')").first
    if not edit_icon.count():
        edit_icon = page.locator("mat-icon:has-text('visibility')").first
    if edit_icon.count():
        edit_icon.click(force=True)
    _wait_loader(page)

    # Detecta condição de Escola Fechada antes de esperar as abas.
    if _is_escola_fechada(page):
        logger.warning(f"[{codigo_inep}] Escola Fechada detectada — formulário pode estar em modo somente-visualização sem abas.")

    # Espera abas; se não aparecerem, tenta fallback de extracão direta.
    try:
        page.wait_for_selector("li.tab-item, mat-form-field", timeout=15000)
    except Exception:
        pass

    # Termo de Sigilo do gestor (se abrir).
    _accept_sigilo_if_present(page)

    # Itera sobre as abas (li.tab-item) do formulário.
    tabs = page.locator("li.tab-item")
    total = tabs.count()

    if total == 0:
        # Fallback para escola fechada ou formulário sem navegação por abas:
        # tenta extrair todos os campos visíveis e distribuí-los nos sheets do modelo.
        logger.warning(f"[{codigo_inep}] Nenhuma aba (li.tab-item) encontrada — tentando extracão direta.")
        _wait_content_ready(page, min_fields=1, timeout=10000)
        for sheet in modelo.all_sheets(model):
            if sheet == modelo.GESTOR_SHEET:
                continue  # já coletado na Fase A
            cols = model.get(sheet, [])
            if not cols:
                continue
            fields = _extract_with_retry(page, cols, max_retries=1)
            if not fields:
                continue
            mapped = _map_to_row(fields, cols)
            mapped["Código do Inep"] = codigo_inep
            mapped["Unidade Escolar"] = nome_unidade
            preenchidos = sum(1 for c, v in mapped.items() if v and c not in modelo.KEY_COLUMNS)
            tot_cols = len([c for c in cols if c not in modelo.KEY_COLUMNS])
            logger.info(f"[{codigo_inep}] Fallback '{sheet}': coletados {preenchidos}/{tot_cols} campos.")
            if preenchidos > 0:
                result[sheet] = mapped
    else:
        for i in range(total):
            tab = page.locator("li.tab-item").nth(i)
            try:
                tab.click(timeout=8000, force=True)
            except Exception:
                continue
            _wait_loader(page)
            _wait_content_ready(page, min_fields=1, timeout=15000)

            tab_label = ""
            try:
                tab_label = (tab.inner_text() or "").strip()
            except Exception:
                pass
            sheet = modelo.resolve_sheet_name(tab_label)
            if sheet not in model or not model.get(sheet):
                continue

            cols = model.get(sheet, [])
            fields = _extract_with_retry(page, cols)
            mapped = _map_to_row(fields, cols)
            mapped["Código do Inep"] = codigo_inep
            mapped["Unidade Escolar"] = nome_unidade

            preenchidos = sum(1 for c, v in mapped.items() if v and c not in modelo.KEY_COLUMNS)
            tot_cols = len([c for c in cols if c not in modelo.KEY_COLUMNS])
            logger.info(f"[{codigo_inep}] Aba '{sheet}': coletados {preenchidos}/{tot_cols} campos.")

            result[sheet] = mapped

    # Fecha o formulário (Cancelar/Fechar) — nunca "Salvar".
    try:
        _fechar_ou_cancelar_gestor(page)
    except Exception:
        pass
    return result


def scrape_gestor_school(page: Page, codigo_inep: str, nome_unidade: str) -> dict[str, dict]:
    """Extrai os dados do GESTOR de UMA escola para todas as abas do modelo
    (Vínculo do gestor, Identificação, Dados pessoais) em modo leitura.

    Retorna {nome_da_aba: {coluna: valor}}.
    """
    _assert_read_only()
    model = modelo.load_model()
    result: dict[str, dict] = {}
    for sh in modelo.all_sheets(model):
        result[sh] = {c: "" for c in model.get(sh, [])}
        result[sh]["Código do Inep"] = codigo_inep
        result[sh]["Unidade Escolar"] = nome_unidade

    # Fase 0: selecionar a escola (mesmos passos do coleta_cadastros_escolas) para fixar
    # o contexto da escola na sessão.
    try:
        _open_school_ficha(page, codigo_inep)
    except SessaoExpirada:
        # Propaga para o loop refazer o login e repetir a escola.
        raise
    except Exception:
        return result

    # Fase A: Vínculo do gestor (lista -> edição).
    try:
        result[modelo.GESTOR_SHEET] = _scrape_gestor_vinculo(page, codigo_inep, nome_unidade)
    except Exception:
        pass

    # Fase B: formulário de cadastro (Identificação + Dados pessoais).
    try:
        edit_rows = _scrape_gestor_edit_form(page, codigo_inep, nome_unidade)
        for sh, row in edit_rows.items():
            result[sh] = row
    except Exception:
        pass

    return result


def _session_expirada(page: Page) -> bool:
    """Detecta se a sessão Keycloak expirou (página de login voltou a aparecer)."""
    try:
        return page.locator("input#username").is_visible()
    except Exception:
        return False


def run_scraping(
    browser: Browser,
    login: str,
    senha: str,
    escolas: list[dict],
    on_progress=None,
    stop_check=None,
) -> list[tuple[dict, dict]]:
    """Varre a lista de escolas em loop, com sessão única reutilizada.

    Fluxo: login uma única vez → loop de escolas (navega para /escola/pesquisar
    entre cada uma) → re-login automático apenas se a sessão Keycloak expirar.

    Para cada escola: extrai dados e devolve (escola, dados_extraidos).
    """
    _assert_read_only()
    outputs: list[tuple[dict, dict]] = []

    # ── Login inicial ──────────────────────────────────────────────────────
    context = browser.new_context()
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
        logger.error("Falha no login inicial. Abortando coleta.")
        _safe_cleanup(context, page)
        return outputs

    logger.info("Login realizado com sucesso. Iniciando loop de escolas.")

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
                if on_progress:
                    on_progress(i, len(escolas), codigo, nome, f"erro: sessão expirada — {exc}")
                continue

        try:
            dados = scrape_gestor_school(page, codigo, nome)

            if stop_check and stop_check():
                if on_progress:
                    on_progress(i, len(escolas), codigo, nome, "interrompido")
                break

            outputs.append((escola, dados))
            if on_progress:
                on_progress(i, len(escolas), codigo, nome, "concluído")

        except SessaoExpirada:
            # Sessão caiu ao abrir a ficha. Re-loga e repete a mesma escola.
            logger.warning(f"[{codigo}] Sessão expirada ao abrir a ficha. Re-logando e repetindo...")
            try:
                _login_and_read(page, login, senha)
                dados = scrape_gestor_school(page, codigo, nome)
                outputs.append((escola, dados))
                if on_progress:
                    on_progress(i, len(escolas), codigo, nome, "concluído")
            except Exception as exc2:  # noqa: BLE001
                logger.error(f"[{codigo}] Falha após re-login: {exc2}")
                if on_progress:
                    on_progress(i, len(escolas), codigo, nome, f"erro: {exc2}")
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[{codigo}] Erro durante coleta: {exc}")
            if on_progress:
                on_progress(i, len(escolas), codigo, nome, f"erro: {exc}")

        # Pequena pausa entre escolas para não sobrecarregar o portal.
        time.sleep(0.3)

    # ── Encerra a sessão única ao final ───────────────────────────────────
    _safe_cleanup(context, page)
    logger.info("Coleta concluída. Sessão encerrada.")
    return outputs
