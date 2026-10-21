"""Login, seleção de escola e retry de sessão compartilhados (Fase 4.3).

Mover 1:1 de rel/rec (cópias idênticas). `raise_if_expired` mora aqui (e não
em `browser`) para evitar import circular — `browser` não importa `session`.
Os scrapers dos apps mantêm os nomes antigos como aliases/wrappers finos:
os monkeypatches dos testes continuam valendo.
"""

from __future__ import annotations

from contextvars import ContextVar

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from apps.common.auth import BASE_URL, _assert_read_only
from apps.common.browser import session_expirada, wait_loader

#: Tentativas de navegação da busca da escola (default 3).
#:
#: A rodada da Coleta Automática baixa para 1: lá a nova tentativa é por
#: escola (o worker roda de novo só as que falharam por timeout).
TENTATIVAS_NAVEGACAO: ContextVar[int] = ContextVar("tentativas_navegacao", default=3)


def tentativas_navegacao() -> int:
    """Tentativas de navegação em vigor neste contexto (default 3)."""
    return TENTATIVAS_NAVEGACAO.get()


class LoginFalhou(Exception):
    """Login não concluído (instabilidade): o botão '#kc-login' não habilitou
    e o formulário de login continuou visível após a tentativa."""


class SessaoExpirada(Exception):
    """A sessão Keycloak expirou (ou a navegação caiu na tela de login) durante
    a abertura da ficha. O chamador deve refazer o login e repetir."""


MOTIVO_INTERROMPIDO = "Coleta interrompida (não processada)"


def login_and_read(page: Page, login: str, senha: str) -> None:
    _assert_read_only()
    page.goto(f"{BASE_URL}/escola/pesquisar", wait_until="domcontentloaded", timeout=30000)
    wait_loader(page)
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


def raise_if_expired(page: Page) -> None:
    """Levanta SessaoExpirada quando a página voltou para a tela de login."""
    if session_expirada(page):
        raise SessaoExpirada()


def accept_sigilo_if_present(page: Page, botao: str = "button:has-text('Continuar')") -> None:
    """Aceita o Termo de Sigilo, se exibido (modo leitura/navegação).

    O termo só habilita o checkbox após rolar o texto até o final. Marcar o
    aceite e clicar 'Continuar' é necessário para ACESSAR a escola (leitura),
    não altera nenhum dado.

    `botao` permite às telas com seletor próprio apontarem o seu botão.
    """
    _assert_read_only()
    try:
        page.wait_for_selector("mat-dialog-container", timeout=1500)
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
    continuar = page.locator(botao).first
    if continuar.count() and continuar.is_enabled():
        continuar.click()
    try:
        page.wait_for_selector("mat-dialog-container", state="detached", timeout=5000)
    except Exception:
        page.wait_for_timeout(500)


def select_school(
    page: Page,
    codigo_inep: str,
    tentativas: int | None = None,
    after_select=None,
) -> bool:
    """Busca a escola pelo código e a seleciona (contexto de sessão).

    Robusto contra o loader travar (retry de navegação) e contra a sessão
    expirar no meio do caminho (levanta `SessaoExpirada`).

    `tentativas=None` usa :data:`TENTATIVAS_NAVEGACAO` (3 nas telas; 1 na
    rodada da Coleta Automática). `after_select(page)` executa um wait
    pós-clique específico do app; o default espera pelo botão
    'Gerar'/modal de relatórios.
    """
    _assert_read_only()
    if tentativas is None:
        tentativas = tentativas_navegacao()
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
            wait_loader(page)
            if session_expirada(page):
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
    wait_loader(page)

    link = page.locator(f"a.cursor-pointer:has-text('{codigo_inep}')").first
    if not link.count():
        return False
    link.click()
    wait_loader(page)
    if after_select is not None:
        after_select(page)
    else:
        try:
            page.wait_for_selector("mat-dialog-container, button:has-text('Gerar')", timeout=10000)
        except Exception:
            pass

    accept_sigilo_if_present(page)
    return True


def marcar_nao_processadas(failures: list[dict], restantes: list[dict]) -> None:
    """Registra como não processadas as escolas que sobrarem quando o loop para.

    Usado nos dois pontos de parada: antes de iniciar a escola (nada foi
    coletado) e depois de coletá-la (o dado parcial é descartado — a escola
    entra na lista para ser recoletada).
    """
    failures.extend(
        {
            "codigo_inep": escola["codigo_inep"],
            "nome_unidade": escola.get("nome_unidade", ""),
            "motivo": MOTIVO_INTERROMPIDO,
        }
        for escola in restantes
    )
