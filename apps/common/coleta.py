"""Motor genérico do laço de coleta compartilhado pelos 4 coletores (Fase 4.4).

O laço canônico é o do coletor de Cadastros; os demais convergem para ele com
diferenças apenas de texto/parametrização. Os callables do app (login, sessão,
pausa, logs e gravação) chegam por `ColetaHooks` — DI no call time — para os
monkeypatches dos testes continuarem valendo.

`scrape_one(context, page, codigo, nome)` devolve os dados da escola ou `None`
quando ela não foi encontrada (o `context` atende ao recibo, que captura o
download pelo contexto).
"""

from __future__ import annotations

import logging
import os
import time
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Callable

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from apps.common.auth import _assert_read_only
from apps.common.session import LoginFalhou, SessaoExpirada


@dataclass(frozen=True)
class ColetaHooks:
    """Callables do app consumidos pelo laço genérico (lidos no call time)."""

    login_and_read: Callable
    session_expirada: Callable
    safe_cleanup: Callable
    pausa_entre_escolas: Callable
    log_tempo_escola: Callable
    registrar_sucesso: Callable
    marcar_nao_processadas: Callable


@dataclass(frozen=True)
class TextosColeta:
    """Textos e formatadores de log específicos de cada coletor."""

    log_abort: str
    log_inicio_loop: str
    formatar_log_erro: Callable[[str, BaseException], str]
    formatar_motivo_relogin: Callable[[BaseException], str]
    formatar_log_nao_encontrada: Callable[[str], str] | None = None
    formatar_log_nao_encontrada_pos_relogin: Callable[[str], str] | None = None
    # Mapeia exceções rotineiras do app para (motivo, progresso); None = genérico.
    mapear_excecao: Callable[[BaseException], tuple[str, str] | None] | None = None


def e_timeout(exc: BaseException) -> bool:
    """True quando a exceção é um timeout do Playwright (qualquer operação).

    O motivo visto pelo usuário é ``Page.wait_for_selector: Timeout 30000ms
    exceeded.`` (ou ``goto``/``click``/download). A rodada da 1ª Etapa usa a
    marca ``"timeout"`` da falha para repetir só aquela escola.
    """
    if isinstance(exc, PlaywrightTimeoutError):
        return True
    texto = str(exc).lower()
    return "timeout" in texto and "exceeded" in texto


#: Teto de tentativas por escola quando o portal estoura timeout (a rodada usa).
MAX_TENTATIVAS_TIMEOUT = 5
#: Espera entre as tentativas de timeout (segundos).
ESPERA_ENTRE_TENTATIVAS = 5.0

#: Tentativas por escola em timeout. Default 1 (sem retry — telas isoladas);
#: a rodada da 1ª Etapa eleva para :data:`MAX_TENTATIVAS_TIMEOUT`.
TENTATIVAS_TIMEOUT: ContextVar[int] = ContextVar("tentativas_timeout", default=1)
#: Espera entre as tentativas de timeout (segundos).
ESPERA_TENTATIVAS: ContextVar[float] = ContextVar(
    "espera_tentativas_timeout", default=ESPERA_ENTRE_TENTATIVAS
)


def tentativas_timeout() -> int:
    """Quantas tentativas a escola ganha quando o Playwright estoura timeout."""
    return max(1, TENTATIVAS_TIMEOUT.get())


def espera_tentativas() -> float:
    """Segundos de espera entre as tentativas de timeout (nunca negativo)."""
    return max(0.0, ESPERA_TENTATIVAS.get())


def esperar_interrompivel(segundos: float, stop_check=None) -> bool:
    """Dorme em fatias curtas checando a interrupção do usuário.

    Devolve ``True`` quando a coleta foi interrompida — a espera para no ato e
    a nova tentativa não acontece.
    """
    restante = max(0.0, segundos)
    while restante > 0:
        if stop_check and stop_check():
            return True
        fatia = min(0.25, restante)
        time.sleep(fatia)
        restante = round(restante - fatia, 6)
    return bool(stop_check and stop_check())


def com_tentativas_timeout(
    scrape_one,
    context,
    page,
    codigo: str,
    nome: str,
    *,
    i: int,
    total: int,
    logger: logging.Logger,
    on_progress=None,
    stop_check=None,
):
    """Coleta uma escola repetindo-a **na hora** quando estoura timeout.

    A fila não avança enquanto as tentativas da escola atual não terminam: na
    rodada (:data:`TENTATIVAS_TIMEOUT` = 5) a escola é repetida até coletar ou
    esgotar as tentativas, com :data:`ESPERA_TENTATIVAS` segundos entre elas (a
    interrupção do usuário vence a espera). Fora da rodada (default 1) o
    comportamento é o de sempre.

    A tentativa que falhou não deixa dados: ``scrape_one`` só devolve quando
    termina e a gravação (:func:`registrar_sucesso`) acontece uma única vez,
    com a tentativa que deu certo.
    """
    limite = tentativas_timeout()
    for tentativa in range(1, limite + 1):
        try:
            return scrape_one(context, page, codigo, nome)
        except Exception as exc:  # noqa: BLE001
            if not e_timeout(exc) or tentativa >= limite:
                raise
            espera = espera_tentativas()
            logger.warning(
                f"[{codigo}] timeout — nova tentativa {tentativa + 1} de {limite} "
                f"em {espera:.0f}s (a fila aguarda esta escola)"
            )
            if on_progress:
                on_progress(
                    i,
                    total,
                    codigo,
                    nome,
                    f"nova tentativa {tentativa + 1} de {limite} (timeout)",
                )
            if esperar_interrompivel(espera, stop_check):
                raise
            # A tentativa recomeça: a tela volta a mostrar a escola atual.
            if on_progress:
                on_progress(i, total, codigo, nome, "Coletando dados ...")


def pausa_entre_escolas() -> float:
    """Pausa entre escolas (CENSO_SLEEP_ESCOLAS; default 0.3s)."""
    try:
        pausa = float(os.environ.get("CENSO_SLEEP_ESCOLAS", "0.3"))
    except ValueError:
        return 0.3
    if not (0 <= pausa < float("inf")):
        return 0.3
    return pausa


def log_tempo_escola(logger: logging.Logger, codigo: str, t0: float) -> None:
    """Loga o tempo decorrido de processamento de uma escola (em segundos)."""
    logger.info(f"[{codigo}] escola processada em {time.monotonic() - t0:.1f}s")


def registrar_sucesso(outputs, on_school_done, escola, dados) -> None:
    """Grava incrementalmente (se houver callback) e acumula para o retorno.

    O callback roda ANTES do append: se a gravação falhar, a exceção vira
    falha da escola (entra em 'não coletadas') — nada some em silêncio.
    """
    if on_school_done is not None:
        on_school_done(escola, dados)
    outputs.append((escola, dados))


def _mascarar_login(texto: str, login: str) -> str:
    """Remove o CPF/login de mensagens do portal antes de logar/exibir.

    Só mascara valores com 6+ caracteres: em testes o login é curto ("l") e a
    substituição ingênua corromperia palavras da própria mensagem.
    """
    if texto and login and len(login) >= 6:
        return texto.replace(login, "***")
    return texto


def _detalhe_falha_login(exc: BaseException | None, login: str) -> str:
    """Motivo legível de uma falha de login (para o log e para a tela)."""
    if isinstance(exc, LoginFalhou):
        detalhe = exc.detalhe or exc.mensagem
        if detalhe:
            return _mascarar_login(detalhe, login)
        return (
            "O formulário de login continuou visível após a tentativa "
            "(login ou senha não aceitos)."
        )
    if exc is None:
        return "Falha de login sem detalhe."
    texto = _mascarar_login(str(exc).strip(), login)
    if texto:
        return f"{type(exc).__name__}: {texto}"
    return f"{type(exc).__name__} (sem detalhe)"


def run_coleta(
    browser,
    login: str,
    senha: str,
    escolas: list[dict],
    *,
    scrape_one,
    hooks: ColetaHooks,
    textos: TextosColeta,
    logger: logging.Logger,
    accept_downloads: bool,
    on_progress=None,
    stop_check=None,
    on_school_done=None,
) -> tuple[list[tuple[dict, Any]], list[dict]]:
    """Varre a lista de escolas em loop, com sessão única reutilizada.

    Fluxo: login uma única vez (2 tentativas em caso de `LoginFalhou` sem
    mensagem do portal), loop de escolas com re-login automático quando a
    sessão Keycloak expirar (antes da escola ou ao abrir a ficha) e
    encerramento da sessão no final.

    Falha no login inicial é **fatal**: o motivo (incluindo a mensagem exibida
    pelo portal, ex.: "Nome de usuário ou senha inválida.") é logado e a função
    levanta `LoginFalhou`, para a rodada parar e orientar o usuário a verificar
    as credenciais — em vez de devolver todas as escolas como "Falha no login"
    e a rodada pausar oferecendo "Continuar".
    """
    _assert_read_only()
    t_inicio = time.monotonic()
    outputs: list[tuple[dict, Any]] = []
    failures: list[dict] = []

    # ── Login inicial ──────────────────────────────────────────────────────
    context = browser.new_context(accept_downloads=accept_downloads)
    page = context.new_page()
    logged_in = False
    ultimo_erro: BaseException | None = None
    for tentativa in range(1, 3):
        try:
            hooks.login_and_read(page, login, senha)
            logged_in = True
            break
        except LoginFalhou as exc:
            ultimo_erro = exc
            detalhe = _detalhe_falha_login(exc, login)
            logger.warning(
                f"Tentativa de login {tentativa}/2 não concluída: {detalhe}"
            )
            # Mensagem do portal = recusa definitiva (senha incorreta, conta
            # bloqueada etc.): repetir não resolve e pode consumir tentativas
            # da conta. Só repete quando a tela não explicou o motivo.
            if exc.mensagem:
                break
            if tentativa < 2:
                time.sleep(1)
            continue
        except Exception as exc:  # noqa: BLE001
            ultimo_erro = exc
            logger.warning(
                "Tentativa de login "
                f"{tentativa}/2 falhou: {_detalhe_falha_login(exc, login)}"
            )
            break

    if not logged_in:
        detalhe = _detalhe_falha_login(ultimo_erro, login)
        logger.error(f"{textos.log_abort} Motivo: {detalhe}")
        hooks.safe_cleanup(context, page)
        mensagem = getattr(ultimo_erro, "mensagem", None)
        if mensagem:
            mensagem = _mascarar_login(str(mensagem), login)
        raise LoginFalhou(mensagem, detalhe=detalhe) from ultimo_erro

    logger.info(textos.log_inicio_loop)

    # ── Loop de escolas (sessão reutilizada) ───────────────────────────────
    for i, escola in enumerate(escolas, 1):
        codigo = escola["codigo_inep"]
        nome = escola.get("nome_unidade", "")
        t0 = time.monotonic()

        if stop_check and stop_check():
            hooks.marcar_nao_processadas(failures, escolas[i - 1:])
            break
        if on_progress:
            on_progress(i - 1, len(escolas), codigo, nome, "Coletando dados ...")

        # Verifica se a sessão ainda está ativa antes de cada escola.
        if hooks.session_expirada(page):
            logger.warning(f"[{codigo}] Sessão expirada. Realizando re-login...")
            try:
                hooks.login_and_read(page, login, senha)
                logger.info(f"[{codigo}] Re-login concluído.")
            except Exception as exc:
                failures.append(
                    {
                        "codigo_inep": codigo,
                        "nome_unidade": nome,
                        "motivo": f"Erro (re-login): {textos.formatar_motivo_relogin(exc)}",
                        "timeout": e_timeout(exc),
                    }
                )
                if on_progress:
                    on_progress(i, len(escolas), codigo, nome, f"erro: sessão expirada — {exc}")
                hooks.log_tempo_escola(codigo, t0)
                continue

        try:
            dados = com_tentativas_timeout(
                scrape_one,
                context,
                page,
                codigo,
                nome,
                i=i,
                total=len(escolas),
                logger=logger,
                on_progress=on_progress,
                stop_check=stop_check,
            )

            if stop_check and stop_check():
                if on_progress:
                    on_progress(i, len(escolas), codigo, nome, "interrompido")
                hooks.marcar_nao_processadas(failures, escolas[i - 1:])
                break

            if dados is None:
                if textos.formatar_log_nao_encontrada:
                    logger.warning(textos.formatar_log_nao_encontrada(codigo))
                failures.append(
                    {"codigo_inep": codigo, "nome_unidade": nome, "motivo": "Escola não encontrada"}
                )
                if on_progress:
                    on_progress(i, len(escolas), codigo, nome, "erro: escola não encontrada")
                continue

            hooks.registrar_sucesso(outputs, on_school_done, escola, dados)
            if on_progress:
                on_progress(i, len(escolas), codigo, nome, "concluído")

        except SessaoExpirada:
            # A sessão caiu durante a abertura da ficha. Refaz o login e repete
            # a mesma escola antes de prosseguir (evita perder o lote inteiro).
            logger.warning(f"[{codigo}] Sessão expirada ao abrir a ficha. Re-logando e repetindo...")
            try:
                hooks.login_and_read(page, login, senha)
            except Exception as exc_re:  # noqa: BLE001
                logger.error(f"[{codigo}] Falha no re-login: {exc_re}")
                failures.append(
                    {
                        "codigo_inep": codigo,
                        "nome_unidade": nome,
                        "motivo": f"Erro (re-login): {textos.formatar_motivo_relogin(exc_re)}",
                        "timeout": e_timeout(exc_re),
                    }
                )
                if on_progress:
                    on_progress(i, len(escolas), codigo, nome, f"erro: sessão expirada — {exc_re}")
                continue

            try:
                dados = com_tentativas_timeout(
                    scrape_one,
                    context,
                    page,
                    codigo,
                    nome,
                    i=i,
                    total=len(escolas),
                    logger=logger,
                    on_progress=on_progress,
                    stop_check=stop_check,
                )
                if dados is None:
                    if textos.formatar_log_nao_encontrada_pos_relogin:
                        logger.warning(textos.formatar_log_nao_encontrada_pos_relogin(codigo))
                    failures.append(
                        {
                            "codigo_inep": codigo,
                            "nome_unidade": nome,
                            "motivo": "Escola não encontrada",
                        }
                    )
                    if on_progress:
                        on_progress(i, len(escolas), codigo, nome, "erro: escola não encontrada")
                else:
                    hooks.registrar_sucesso(outputs, on_school_done, escola, dados)
                    if on_progress:
                        on_progress(i, len(escolas), codigo, nome, "concluído")
            except Exception as exc2:  # noqa: BLE001
                logger.error(f"[{codigo}] Falha após re-login: {exc2}")
                failures.append(
                    {
                        "codigo_inep": codigo,
                        "nome_unidade": nome,
                        "motivo": f"Erro (após re-login): {exc2}",
                        "timeout": e_timeout(exc2),
                    }
                )
                if on_progress:
                    on_progress(i, len(escolas), codigo, nome, f"erro: {exc2}")
        except Exception as exc:  # noqa: BLE001
            mapeado = textos.mapear_excecao(exc) if textos.mapear_excecao else None
            if mapeado is not None:
                # Exceção rotineira do app: motivo/progresso próprios, sem log
                # de erro (comportamento do baseline de Relatórios/Recibos).
                motivo, progresso = mapeado
                failures.append(
                    {
                        "codigo_inep": codigo,
                        "nome_unidade": nome,
                        "motivo": motivo,
                        "timeout": False,
                    }
                )
                if on_progress:
                    on_progress(i, len(escolas), codigo, nome, progresso)
            else:
                logger.error(textos.formatar_log_erro(codigo, exc))
                failures.append(
                    {
                        "codigo_inep": codigo,
                        "nome_unidade": nome,
                        "motivo": f"Erro: {exc}",
                        "timeout": e_timeout(exc),
                    }
                )
                if on_progress:
                    on_progress(i, len(escolas), codigo, nome, f"erro: {exc}")
        finally:
            hooks.log_tempo_escola(codigo, t0)

        # Pequena pausa entre escolas para não sobrecarregar o portal.
        time.sleep(hooks.pausa_entre_escolas())

    # ── Encerra a sessão única ao final ───────────────────────────────────
    hooks.safe_cleanup(context, page)
    tempo_total = time.monotonic() - t_inicio
    logger.info(
        f"Coleta concluída: {len(outputs)} escola(s) coletada(s), {len(failures)} falha(s), "
        f"{tempo_total:.1f}s no total ({tempo_total / max(1, len(escolas)):.1f}s por escola em média). "
        "Sessão encerrada."
    )
    return outputs, failures
