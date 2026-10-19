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

import logging
import time

from playwright.sync_api import Browser, Page

from apps.common import browser as _browser
from apps.common import coleta as _coleta
from apps.common import session as _session

from . import modelo
from .auth import BASE_URL, _assert_read_only

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


# Aliases de `apps.common` (Fase 4.7) — preservam os monkeypatches dos testes:
# os nomes continuam morando neste módulo e são lidos no call time.
_safe_cleanup = _browser.safe_cleanup
_wait_loader = _browser.wait_loader


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


_session_expirada = _browser.session_expirada

LoginFalhou = _session.LoginFalhou
SessaoExpirada = _session.SessaoExpirada

_login_and_read = _session.login_and_read


_accept_sigilo_if_present = _session.accept_sigilo_if_present


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
            page.goto(f"{BASE_URL}/escola/pesquisar", wait_until="domcontentloaded", timeout=30000)
            # O portão real é o campo de busca (ou a tela de login) aparecer.
            try:
                page.wait_for_selector(
                    "input#username, input[formcontrolname='codigoEscola']", timeout=15000
                )
            except Exception:
                pass
            _wait_loader(page)
            # Se a navegação caiu na tela de login, a sessão expirou.
            if _session_expirada(page):
                raise SessaoExpirada()
            page.wait_for_selector("input[formcontrolname='codigoEscola']", timeout=30000)
            break
        except SessaoExpirada:
            raise
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            page.wait_for_timeout(3000)
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


def scrape_school(page: Page, codigo_inep: str, nome_unidade: str) -> dict[str, dict] | None:
    """Extrai os dados de UMA escola para as 6 abas do modelo (apenas leitura).

    Devolve None quando a ficha da escola não abre (não encontrada), para que
    o chamador registre a falha na planilha de escolas não coletadas.
    """
    _assert_read_only()
    result: dict[str, dict] = {}

    if not _open_school_ficha(page, codigo_inep):
        return None

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


_MOTIVO_INTERROMPIDO = _session.MOTIVO_INTERROMPIDO
_marcar_nao_processadas = _session.marcar_nao_processadas


def _pausa_entre_escolas() -> float:
    """Wrapper de `apps.common.coleta` (histórico): pausa entre escolas."""
    return _coleta.pausa_entre_escolas()


def _log_tempo_escola(codigo: str, t0: float) -> None:
    """Wrapper de `apps.common.coleta` (histórico): fecha o log de tempo do app."""
    return _coleta.log_tempo_escola(logger, codigo, t0)


def _registrar_sucesso(outputs, on_school_done, escola, dados) -> None:
    """Wrapper de `apps.common.coleta` (histórico): registra a escola coletada."""
    return _coleta.registrar_sucesso(outputs, on_school_done, escola, dados)


_TEXTOS = _coleta.TextosColeta(
    log_abort="Falha no login inicial. Abortando coleta.",
    log_inicio_loop="Login realizado com sucesso. Iniciando loop de escolas.",
    formatar_log_erro=lambda codigo, exc: f"[{codigo}] Erro durante coleta: {exc}",
    formatar_motivo_relogin=lambda exc: str(exc) or type(exc).__name__,
    formatar_log_nao_encontrada=lambda codigo: f"[{codigo}] Escola não encontrada.",
    formatar_log_nao_encontrada_pos_relogin=(
        lambda codigo: f"[{codigo}] Escola não encontrada após re-login."
    ),
)


def run_scraping(
    browser: Browser,
    login: str,
    senha: str,
    escolas: list[dict],
    on_progress=None,
    stop_check=None,
    on_school_done=None,
) -> tuple[list[tuple[dict, dict]], list[dict]]:
    """Wrapper de `apps.common.coleta` (histórico): coleta dos dados cadastrais."""

    def _scrape_one(context, page, codigo: str, nome: str):
        return scrape_school(page, codigo, nome)

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
        accept_downloads=False,
        on_progress=on_progress,
        stop_check=stop_check,
        on_school_done=on_school_done,
    )
