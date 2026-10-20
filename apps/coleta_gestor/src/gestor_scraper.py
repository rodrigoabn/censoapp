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

import logging
import re
import time

from playwright.sync_api import Browser, Page

from apps.common import browser as _browser
from apps.common import coleta as _coleta
from apps.common import session as _session

from . import modelo
from .auth import BASE_URL, _assert_read_only

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


# Aliases de `apps.common` (Fase 4.7) — preservam os monkeypatches dos testes:
# os nomes continuam morando neste módulo e são lidos no call time.
_safe_cleanup = _browser.safe_cleanup


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


LoginFalhou = _session.LoginFalhou
SessaoExpirada = _session.SessaoExpirada

_login_and_read = _session.login_and_read


def _accept_sigilo_if_present(page: Page) -> None:
    """Wrapper de `apps.common.session` (histórico): botão próprio da tela do gestor."""
    return _session.accept_sigilo_if_present(
        page, botao="mat-dialog-container button:has-text('Continuar')"
    )


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


def _fechar_todos_dialogos(page: Page, max_tentativas: int = 3) -> None:
    """Fecha diálogos abertos sem salvar (Escape e, se preciso, Cancelar/Fechar)."""
    for _ in range(max_tentativas):
        try:
            if page.locator("mat-dialog-container").count() == 0:
                break
        except Exception:
            break
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)
        except Exception:
            pass
        try:
            if page.locator("mat-dialog-container").count() == 0:
                break
        except Exception:
            break
        _fechar_ou_cancelar_gestor(page)
    # Formulário aberto em rota (sem modal): botão Cancelar/Fechar, se houver.
    try:
        _fechar_ou_cancelar_gestor(page)
    except Exception:
        pass


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


def _extract_vinculo(page: Page, cols: list[str], timeout: int = 20000) -> list[dict]:
    """Extrai campos do vínculo aguardando o formulário abrir.

    A tela de pesquisa atrás do formulário também tem mat-form-fields; por isso
    a espera é pelo mapeamento de ao menos uma coluna do modelo de vínculo,
    não pela simples presença de campos.
    """
    deadline = time.monotonic() + (timeout / 1000)
    fields: list[dict] = []
    while time.monotonic() < deadline:
        try:
            fields = page.evaluate(_EXTRACT_JS)
        except Exception:
            fields = []
        mapped = _map_to_row(fields, cols)
        if any(v and c not in modelo.KEY_COLUMNS for c, v in mapped.items()):
            return fields
        page.wait_for_timeout(500)
    return fields


def _scrape_gestor_vinculo(page: Page, codigo_inep: str, nome_unidade: str) -> dict:
    """Fase A — coleta a aba 'Vínculo do gestor' via list -> editing."""
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

    # O ícone "visibility"/"edit" da PÁGINA é dos dados cadastrais (Fase B),
    # e fica atrás do backdrop enquanto o modal está aberto. A ação da linha
    # dentro do modal é "editing" — é ela que abre o formulário do vínculo.
    try:
        page.wait_for_selector("mat-dialog-container", timeout=15000)
    except Exception:
        logger.warning(f"[{codigo_inep}] Modal de vínculos não abriu.")
        return row

    dialog = page.locator("mat-dialog-container").last
    editing = dialog.locator("mat-icon:has-text('editing')").first
    if not editing.count():
        logger.warning(f"[{codigo_inep}] Ícone 'editing' do vínculo não encontrado no modal.")
        _fechar_todos_dialogos(page)
        return row

    try:
        editing.click(force=True)
        _wait_loader(page)
        _accept_sigilo_if_present(page)
        fields = _extract_vinculo(page, cols)

        mapped = _map_to_row(fields, cols)
        mapped["Código do Inep"] = codigo_inep
        mapped["Unidade Escolar"] = nome_unidade

        preenchidos = sum(1 for c, v in mapped.items() if v and c not in modelo.KEY_COLUMNS)
        tot_cols = len([c for c in cols if c not in modelo.KEY_COLUMNS])
        logger.info(f"[{codigo_inep}] Vínculo: coletados {preenchidos}/{tot_cols} campos.")
        return mapped
    finally:
        _fechar_todos_dialogos(page)


def _buscar_icone_edicao(page: Page):
    """Localiza o ícone que abre o cadastro do gestor (cascata de seletores)."""
    edit_icon = page.locator("mat-icon[mattooltip*='dados cadastrais']").first
    if not edit_icon.count():
        edit_icon = page.locator("mat-icon[mattooltip*='editar os dados cadastrais']").first
    if not edit_icon.count():
        edit_icon = page.locator("mat-icon[mattooltip*='visualizar os dados cadastrais']").first
    if not edit_icon.count():
        edit_icon = page.locator("mat-icon:has-text('edit')").first
    if not edit_icon.count():
        edit_icon = page.locator("mat-icon:has-text('visibility')").first
    return edit_icon


def _scrape_gestor_edit_form(
    page: Page, codigo_inep: str, nome_unidade: str, reload: bool = True
) -> dict[str, dict]:
    """Fase B — abre o formulário de cadastro do gestor (ícone 'edit') e coleta
    as abas 'Identificação' e 'Dados pessoais' (e quaisquer outras abas
    existentes no formulário), espelhando o padrão do coleta_cadastros_escolas.

    Com `reload=False`, reaproveita a lista que a Fase A acabou de deixar
    aberta na página e só navega de novo se o ícone não estiver disponível.

    Retorna {nome_da_aba: {coluna: valor}}. Não altera nenhum dado (modo
    leitura). Ao final, clica em 'Cancelar' para fechar o formulário.
    """
    _assert_read_only()
    model = modelo.load_model()
    result: dict[str, dict] = {}

    if reload:
        n = _abrir_pesquisa_gestor(page)
        if n == 0:
            return result

    # Abrir o cadastro do gestor (ícone "edit" ou "visibility").
    edit_icon = _buscar_icone_edicao(page)
    if not edit_icon.count() and not reload:
        # Fallback: a lista não está na página (Fase B fora de sequência) —
        # navega até ela e rebusca o ícone.
        n = _abrir_pesquisa_gestor(page)
        if n == 0:
            return result
        edit_icon = _buscar_icone_edicao(page)
    if edit_icon.count():
        edit_icon.click(force=True)
    _wait_loader(page)

    # Detecta condição de Escola Fechada antes de esperar as abas.
    if _is_escola_fechada(page):
        logger.warning(f"[{codigo_inep}] Escola Fechada detectada — formulário pode estar em modo somente-visualização sem abas.")

    # Espera as abas do cadastro do gestor. "mat-form-field" sozinho não serve:
    # a tela de pesquisa atrás do formulário também tem campos e liberaria a
    # espera cedo demais (era o que fazia o fallback ler os filtros da busca).
    try:
        page.wait_for_selector("li.tab-item", timeout=25000)
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


def scrape_gestor_school(page: Page, codigo_inep: str, nome_unidade: str) -> dict[str, dict] | None:
    """Extrai os dados do GESTOR de UMA escola para todas as abas do modelo
    (Vínculo do gestor, Identificação, Dados pessoais) em modo leitura.

    Devolve {nome_da_aba: {coluna: valor}}, ou None quando a ficha da escola
    não abre (não encontrada), para o chamador registrar a falha.
    """
    _assert_read_only()
    model = modelo.load_model()
    result: dict[str, dict] = {}
    for sh in modelo.all_sheets(model):
        result[sh] = {c: "" for c in model.get(sh, [])}
        result[sh]["Código do Inep"] = codigo_inep
        result[sh]["Unidade Escolar"] = nome_unidade

    # Fase 0: selecionar a escola (mesmos passos do coleta_cadastros_escolas) para fixar
    # o contexto da escola na sessão. Sem abertura, entra em "não coletadas".
    if not _open_school_ficha(page, codigo_inep):
        return None

    # Fase A: Vínculo do gestor (lista -> edição).
    try:
        result[modelo.GESTOR_SHEET] = _scrape_gestor_vinculo(page, codigo_inep, nome_unidade)
    except Exception:
        pass

    # Fase B: formulário de cadastro (Identificação + Dados pessoais).
    try:
        edit_rows = _scrape_gestor_edit_form(page, codigo_inep, nome_unidade, reload=False)
        for sh, row in edit_rows.items():
            result[sh] = row
    except Exception:
        pass

    return result


_session_expirada = _browser.session_expirada
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
    """Wrapper de `apps.common.coleta` (histórico): coleta do vínculo do gestor."""

    def _scrape_one(context, page, codigo: str, nome: str):
        return scrape_gestor_school(page, codigo, nome)

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
