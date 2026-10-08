"""Scraper do Educacenso em MODO LEITURA (Playwright).

Fluxo calibrado (inspeção ao vivo, apenas leitura):
  1. Login via Keycloak (acesso.inep.gov.br) com CPF + senha.
  2. Busca da escola em /escola/pesquisar pelo código Inep.
  3. Abertura da ficha em /escola/cadastro/dados-cadastrais.
  4. Para cada aba (li.tab-item) extrai os campos (mat-form-field) e mapeia
     os valores para as colunas da 2ª linha do modelo_coleta.xlsx.

NUNCA preenche, marca ou submete dados de questionário no site.
"""

from __future__ import annotations

import time
import logging

from playwright.sync_api import Browser, Page, TimeoutError as PlaywrightTimeoutError

import src.modelo as modelo
from src.auth import BASE_URL, READ_ONLY, _assert_read_only

logger = logging.getLogger("coleta_cadastros_escolas")

TAB_NAMES = [
    "Vinculação institucional e Convênio",
    "Funcionamento e Identificação",
    "Estrutura física",
    "Equipamentos e recursos tecnológicos",
    "Recursos humanos",
    "Organização escolar",
]

# Script de extração executado no browser (apenas leitura do DOM).
# Captura: (1) mat-form-field (selects/inputs com label em aria-label,
# placeholder ou <span> irmão), (2) mat-checkbox de múltipla escolha
# (label no .mat-checkbox-label; valor "Sim" se marcado) e (3) campos de
# texto estático (ex.: "4 - Entidade superior da escola") cujo valor aparece
# num <span> irmão/próximo, fora de mat-form-field.
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
      // Recursos humanos: o rótulo fica num <span> em ancestral/irmão
      // acima do mat-form-field (não é filho direto). Sobe até 4 níveis.
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
  // (3) Campos de texto estático: <label> conhecido seguido do valor num
  // <span> irmão/próximo, fora de mat-form-field (ex.: "4 - Entidade superior
  // da escola" -> "SECRETARIA MUNICIPAL ..."). Só atua em labels conhecidos
  // do modelo, evitando capturar mat-form-field ou cabeçalho do usuário.
  const KNOWN_STATIC = [
    '4 - Entidade superior da escola'
  ];
  const root = document.querySelector('.tab-content') || document.body;
  root.querySelectorAll('label').forEach(lab => {
    const t = (lab.innerText || '').trim();
    if (!KNOWN_STATIC.includes(t)) return;
    // valor está num <span> dentro do <li>/<ul> irmão após o label
    let node = lab;
    for (let i = 0; i < 3 && node; i++) {
      node = node.parentElement;
      const sp = node ? node.querySelector('span') : null;
      if (sp) {
        const val = sp.innerText.trim();
        if (val && val.toUpperCase().indexOf('ENTIDADE SUPERIOR') < 0) {
          push(t, val);
          return;
        }
      }
    }
  });
  return out;
}"""


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
        # overlay pode nem ter aparecido; ignora.
        pass


def _wait_content_ready(page: Page, min_fields: int = 1, timeout: int = 15000) -> bool:
    """Faz um polling para garantir que o formulário Angular do site terminou
    de renderizar os dados nos campos (mat-form-field).

    Evita que façamos a extração em um DOM recém-carregado porém vazio.
    """
    _wait_loader(page)
    start_time = time.time()
    while time.time() - start_time < (timeout / 1000.0):
        try:
            count = page.evaluate('''() => {
                let filled = 0;
                // Inputs de texto/number
                document.querySelectorAll('input, select, textarea').forEach(el => {
                    if (el.value && el.value.trim() !== '') {
                        filled++;
                    }
                });
                // Checkboxes/Radios selecionados
                document.querySelectorAll('mat-checkbox.mat-checkbox-checked, mat-radio-button.mat-radio-checked').forEach(el => {
                    filled++;
                });
                // Mat-selects que mostram valor selecionado no texto do display
                document.querySelectorAll('mat-select .mat-select-value').forEach(el => {
                    if (el.textContent && el.textContent.trim() !== '') {
                        filled++;
                    }
                });
                return filled;
            }''')
            if count >= min_fields:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def _session_expirada(page: Page) -> bool:
    """Detecta se a sessão Keycloak expirou (página de login voltou)."""
    try:
        return page.locator("input#username").is_visible()
    except Exception:
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
    aceite e clicar 'Continuar' é necessário para ACESSAR a ficha (leitura),
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
    continuar = page.locator("button:has-text('Continuar')").first
    if continuar.count() and continuar.is_enabled():
        continuar.click()
    page.wait_for_timeout(3000)


def _open_school_ficha(page: Page, codigo_inep: str, tentativas: int = 3) -> bool:
    """Busca a escola pelo código e abre a ficha de dados cadastrais (leitura).

    É robusto contra duas falhas intermitentes do portal:
      - o overlay `ngx-ui-loader` travar e o campo `codigoEscola` não renderizar
        a tempo (fazemos retry da navegação);
      - a sessão Keycloak expirar no meio do caminho e a página cair na tela de
        login (levantamos `SessaoExpirada` para o chamador refazer o login).
    """
    _assert_read_only()
    last_exc: Exception | None = None
    for _ in range(max(1, tentativas)):
        try:
            page.goto(f"{BASE_URL}/escola/pesquisar", wait_until="domcontentloaded", timeout=15000)
            _wait_loader(page)
            # Se a navegação caiu na tela de login, a sessão expirou.
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
    return page.locator("li.tab-item").count() > 0


def _map_to_model(sheet: str, fields: list[dict]) -> dict:
    """Mapeia os campos extraídos para as colunas da 2ª linha do modelo.

    Usa três estratégias, nesta ordem:
      1. Alias explícito (modelo.resolve_field_label).
      2. Igualdade exata dos rótulos normalizados.
      3. Substring: o rótulo do modelo está contido no do site (ou vice-versa),
         desde que a parte comum tenha ao menos 6 caracteres (evita falsos
         positivos de rótulos curtos).
    """
    sheet_name = modelo.resolve_sheet_name(sheet)
    model = modelo.load_model()
    cols = model.get(sheet_name, [])
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
        # do modelo) casem incidentalmente com rótulos LONGOs onde estão
        # "escondidos" no meio. Ex.: "federal"/"estadual"/"municipal" (curtos)
        # não devem sobrescrever o atributo "2 - Regulamentação/autorização...
        # no conselho ou órgão municipal, estadual ou federal de educação"
        # (caso de escolas fechadas, onde o site expõe essas opções à parte).
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


def scrape_school(page: Page, codigo_inep: str, nome_unidade: str) -> dict[str, dict]:
    """Extrai os dados de UMA escola para as 6 abas do modelo (apenas leitura)."""
    _assert_read_only()
    result: dict[str, dict] = {}

    if not _open_school_ficha(page, codigo_inep):
        for tab in TAB_NAMES:
            sheet_name = modelo.resolve_sheet_name(tab)
            cols = modelo.load_model().get(sheet_name, [])
            result[sheet_name] = {c: "" for c in cols}
        return result

    for tab in TAB_NAMES:
        sheet_name = modelo.resolve_sheet_name(tab)
        try:
            _wait_loader(page)
            page.locator(f"li.tab-item:has-text('{tab}')").first.click(timeout=8000, force=True)
            _wait_loader(page)
            _wait_content_ready(page, min_fields=1, timeout=15000)
        except Exception:
            result[sheet_name] = {c: "" for c in modelo.load_model().get(sheet_name, [])}
            continue
        fields = page.evaluate(_EXTRACT_JS)
        row = _map_to_model(tab, fields)
        row["Código do Inep"] = codigo_inep
        row["Unidade Escolar"] = nome_unidade
        result[sheet_name] = row
    return result


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
            dados = scrape_school(page, codigo, nome)

            if stop_check and stop_check():
                if on_progress:
                    on_progress(i, len(escolas), codigo, nome, "interrompido")
                break

            outputs.append((escola, dados))
            if on_progress:
                on_progress(i, len(escolas), codigo, nome, "concluído")

        except SessaoExpirada:
            # A sessão caiu durante a abertura da ficha. Refaz o login e repete
            # a mesma escola antes de prosseguir (evita perder o lote inteiro).
            logger.warning(f"[{codigo}] Sessão expirada ao abrir a ficha. Re-logando e repetindo...")
            try:
                _login_and_read(page, login, senha)
                dados = scrape_school(page, codigo, nome)
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
