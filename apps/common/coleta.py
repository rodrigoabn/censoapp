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
from dataclasses import dataclass
from typing import Any, Callable

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

    Fluxo: login uma única vez (2 tentativas em caso de `LoginFalhou`), loop de
    escolas com re-login automático quando a sessão Keycloak expirar (antes da
    escola ou ao abrir a ficha) e encerramento da sessão no final.
    """
    _assert_read_only()
    t_inicio = time.monotonic()
    outputs: list[tuple[dict, Any]] = []
    failures: list[dict] = []

    # ── Login inicial ──────────────────────────────────────────────────────
    context = browser.new_context(accept_downloads=accept_downloads)
    page = context.new_page()
    logged_in = False
    for _attempt in range(2):
        try:
            hooks.login_and_read(page, login, senha)
            logged_in = True
            break
        except LoginFalhou:
            time.sleep(1)
            continue
        except Exception:
            break

    if not logged_in:
        logger.error(textos.log_abort)
        failures.extend(
            {
                "codigo_inep": e["codigo_inep"],
                "nome_unidade": e.get("nome_unidade", ""),
                "motivo": "Falha no login",
            }
            for e in escolas
        )
        hooks.safe_cleanup(context, page)
        return outputs, failures

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
                    }
                )
                if on_progress:
                    on_progress(i, len(escolas), codigo, nome, f"erro: sessão expirada — {exc}")
                hooks.log_tempo_escola(codigo, t0)
                continue

        try:
            dados = scrape_one(context, page, codigo, nome)

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
                    }
                )
                if on_progress:
                    on_progress(i, len(escolas), codigo, nome, f"erro: sessão expirada — {exc_re}")
                continue

            try:
                dados = scrape_one(context, page, codigo, nome)
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
                    {"codigo_inep": codigo, "nome_unidade": nome, "motivo": motivo}
                )
                if on_progress:
                    on_progress(i, len(escolas), codigo, nome, progresso)
            else:
                logger.error(textos.formatar_log_erro(codigo, exc))
                failures.append(
                    {"codigo_inep": codigo, "nome_unidade": nome, "motivo": f"Erro: {exc}"}
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
