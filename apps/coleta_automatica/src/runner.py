"""A rodada da Coleta Automática: as etapas, uma após a outra, em background.

A thread **não** toca em `st.*`; ela publica o que está acontecendo no
dicionário `estado` (protegido por `lock`), que a tela lê a cada rerun.

Regras da rodada:

- as etapas rodam **em sequência**, na ordem do registro;
- erro do worker ⇒ a etapa é "falhou" e a **rodada para**;
- etapa que rodou sem erro mas **não coletou nenhuma escola** ⇒ a rodada
  **pausa** e pergunta ao usuário se deve continuar;
- escola que falhou por **timeout** do Playwright ⇒ a escola é repetida **na
  hora** (no máximo 5 tentativas no total, 5 s entre elas) e a fila só avança
  quando as tentativas dela terminarem; a tentativa que deu certo é a única que
  fica no artefato;
- o usuário pode interromper a rodada a qualquer momento (o `stop_check` do
  coletor encerra a etapa em andamento com segurança).
"""

from __future__ import annotations

import shutil
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from apps.common.coleta import (
    ESPERA_ENTRE_TENTATIVAS,
    ESPERA_TENTATIVAS,
    MAX_TENTATIVAS_TIMEOUT,
    TENTATIVAS_TIMEOUT,
)
from apps.common.export import build_pending_xlsx, output_filename, remover_temp
from apps.common.session import TENTATIVAS_NAVEGACAO

from .etapas import Etapa

#: Situações possíveis de uma etapa dentro da rodada.
SITUACOES = (
    "pendente",
    "em_andamento",
    "concluida",
    "concluida_sem_dados",
    "falhou",
    "interrompida",
    "nao_executada",
)


@dataclass
class ResultadoEtapa:
    """O que a rodada sabe sobre uma etapa ao fim (ou durante) dela."""

    chave: str
    titulo: str
    situacao: str
    segundos: float
    caminho_artefato: str | None = None
    caminho_pendencias: str | None = None
    motivo: str | None = None


def _aguardar_confirmacao(
    continuar_event: threading.Event | None,
    stop_event: threading.Event,
) -> bool:
    """Espera o usuário responder "continuar".

    Devolve ``True`` para seguir para a próxima etapa e ``False`` quando a
    rodada foi encerrada durante a espera. Sem ``continuar_event`` (rodada sem
    canal de confirmação) a espera é dispensada e a rodada segue.
    """
    if continuar_event is None:
        return not stop_event.is_set()
    while True:
        if stop_event.is_set():
            return False
        if continuar_event.wait(timeout=0.2):
            continuar_event.clear()
            return True


def montar_pacote(resultados: Sequence[ResultadoEtapa], pasta_base: Path) -> Path | None:
    """Reúne os artefatos das etapas em um ZIP único, uma pasta por etapa.

    Devolve o caminho do ZIP criado ou ``None`` quando nenhuma etapa produziu
    artefato.
    """
    com_artefato = [r for r in resultados if r.caminho_artefato]
    if not com_artefato:
        return None

    pasta_base = Path(pasta_base)
    pasta_base.mkdir(parents=True, exist_ok=True)
    destino = pasta_base / output_filename("coleta_completa", ext=".zip")
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as pacote:
        for resultado in com_artefato:
            arquivo = Path(resultado.caminho_artefato)
            pasta = _pasta_da_etapa(resultado.chave)
            pacote.write(arquivo, f"{pasta}/{arquivo.name}")
            if resultado.caminho_pendencias:
                pendencias = Path(resultado.caminho_pendencias)
                pacote.write(pendencias, f"{pasta}/{pendencias.name}")
    return destino


def _pasta_da_etapa(chave: str) -> str:
    """Nome da pasta da etapa dentro do ZIP (o do registro de etapas)."""
    from .etapas import etapa_por_chave

    try:
        return etapa_por_chave(chave).pasta
    except KeyError:
        return chave


def limpar_temporarios_antigos(horas: int = 24) -> int:
    """Remove as pastas de rodadas abandonadas (órfãs) do diretório temporário.

    Uma rodada abandonada ao trocar de tela deixa a pasta para trás (o estado
    da sessão é apagado na troca). As pastas são removidas quando são velhas —
    de propósito, para não apagar a rodada de outra sessão em uso.
    """
    import time

    limite = time.time() - horas * 3600
    removidas = 0
    for pasta in Path(tempfile.gettempdir()).glob("coleta_automatica_tmp_*"):
        try:
            if pasta.stat().st_mtime < limite:
                shutil.rmtree(pasta, ignore_errors=True)
                removidas += 1
        except OSError:
            continue
    return removidas


def _executar_etapa(
    indice: int,
    etapa: Etapa,
    login: str,
    senha: str,
    escolas: list[dict],
    stop_event: threading.Event,
    lock: threading.Lock,
    estado: dict,
    pasta_base: Path,
    resultados: list[ResultadoEtapa],
    publicar,
    registrar,
    marcar_restantes,
    continuar_event: threading.Event | None,
) -> None:
    """Executa UMA etapa e classifica o resultado (ver o laço de
    :func:`executar_rodada`).

    A etapa roda em uma única chamada do worker: a escola que estoura timeout
    é repetida **na hora** pelo laço compartilhado (até
    :data:`MAX_TENTATIVAS_TIMEOUT` tentativas, :data:`ESPERA_ENTRE_TENTATIVAS`
    segundos entre elas), sem a fila avançar.
    """
    # Interrupção pedida antes de começar esta etapa.
    if stop_event.is_set():
        marcar_restantes(indice)
        publicar(interrompida=True)
        return

    # A pasta de trabalho da etapa é separada da pasta do artefato: a
    # limpeza dos temporários não pode apagar o resultado entregue.
    pasta_etapa = pasta_base / "_trabalho" / etapa.chave
    pasta_etapa.mkdir(parents=True, exist_ok=True)
    shared: dict[str, Any] = {
        "current": None,
        "last": None,
        "count": 0,
        "total": len(escolas),
        "done": False,
        "error": None,
        "interrupted": False,
        "failures": [],
        "aviso": None,
    }
    publicar(
        etapa_atual=etapa.chave,
        shared_etapa=shared,
        aguardando=None,
        etapa_inicio=datetime.now(),
    )

    t0 = time.monotonic()

    # Na rodada: a escola com timeout é repetida na hora (5 tentativas, 5 s) e
    # a navegação interna tenta uma vez só. As telas individuais rodam em outra
    # thread (contexto próprio) e mantêm os defaults (1 tentativa / 3).
    tokens = (
        (TENTATIVAS_TIMEOUT, TENTATIVAS_TIMEOUT.set(MAX_TENTATIVAS_TIMEOUT)),
        (ESPERA_TENTATIVAS, ESPERA_TENTATIVAS.set(ESPERA_ENTRE_TENTATIVAS)),
        (TENTATIVAS_NAVEGACAO, TENTATIVAS_NAVEGACAO.set(1)),
    )
    try:
        etapa.worker(
            etapa.config, login, senha, escolas, stop_event, lock, shared, pasta_etapa
        )
    finally:
        for variavel, token in reversed(tokens):
            variavel.reset(token)

    segundos = time.monotonic() - t0

    # Falha do worker: a etapa falhou e a rodada para.
    erro = shared.get("error")
    if erro:
        registrar(
            ResultadoEtapa(
                chave=etapa.chave,
                titulo=etapa.titulo,
                situacao="falhou",
                segundos=segundos,
                motivo=str(erro),
            )
        )
        marcar_restantes(indice + 1)
        publicar(
            interrompida=True,
            etapa_atual=None,
            shared_etapa=None,
        )
        return

    # Interrompida no meio da etapa: o artefato parcial é guardado, mas a
    # etapa não conta como concluída e a rodada para.
    interrompida = stop_event.is_set()

    # Rodou sem erro, mas não coletou nenhuma escola: a rodada pausa e
    # pergunta ao usuário se deve continuar.
    if not interrompida and not shared.get("count", 0):
        registrar(
            ResultadoEtapa(
                chave=etapa.chave,
                titulo=etapa.titulo,
                situacao="concluida_sem_dados",
                segundos=segundos,
            )
        )
        publicar(aguardando=etapa.chave)
        if not _aguardar_confirmacao(continuar_event, stop_event):
            marcar_restantes(indice + 1)
            publicar(
                interrompida=True,
                etapa_atual=None,
                shared_etapa=None,
            )
            return
        publicar(aguardando=None)
        remover_temp(pasta_etapa)
        return

    # Etapa concluída (ou interrompida com dados parciais): monta o artefato
    # (e a planilha de pendências).
    pasta_artefato = pasta_base / etapa.pasta
    pasta_artefato.mkdir(parents=True, exist_ok=True)
    construtor = getattr(
        etapa.zipper, etapa.config.get("construtor_arquivo", "build_zip")
    )
    caminho_artefato = pasta_artefato / etapa.zipper.output_filename(
        etapa.config["zip_prefix"]
    )
    caminho_artefato.write_bytes(construtor(tmp_dir=pasta_etapa))

    caminho_pendencias = None
    falhas = shared.get("failures") or []
    if falhas:
        caminho_pendencias = pasta_artefato / etapa.zipper.pending_filename(
            etapa.config["zip_prefix"]
        )
        caminho_pendencias.write_bytes(build_pending_xlsx(falhas))

    registrar(
        ResultadoEtapa(
            chave=etapa.chave,
            titulo=etapa.titulo,
            situacao="interrompida" if interrompida else "concluida",
            segundos=segundos,
            caminho_artefato=str(caminho_artefato),
            caminho_pendencias=str(caminho_pendencias) if caminho_pendencias else None,
        )
    )
    remover_temp(pasta_etapa)

    if interrompida:
        # A rodada foi interrompida no meio da etapa: o que já foi
        # coletado fica disponível, mas as etapas seguintes não rodam e
        # o pacote completo não é gerado.
        marcar_restantes(indice + 1)
        publicar(
            interrompida=True,
            etapa_atual=None,
            shared_etapa=None,
        )


def executar_rodada(
    etapas: Sequence[Etapa],
    login: str,
    senha: str,
    escolas: list[dict],
    *,
    stop_event: threading.Event,
    lock: threading.Lock,
    estado: dict,
    pasta_base: Path,
    continuar_event: threading.Event | None = None,
) -> None:
    """Executa as etapas em sequência e publica o progresso em ``estado``.

    ``estado`` recebe as chaves ``resultados`` (lista de
    :class:`ResultadoEtapa`), ``etapa_atual``, ``shared_etapa`` (o ``shared``
    da etapa em curso, para a linha viva), ``aguardando`` (a etapa que
    pausou a rodada), ``interrompida`` e ``pacote``.
    """
    resultados: list[ResultadoEtapa] = estado.setdefault("resultados", [])
    pasta_base = Path(pasta_base)
    pasta_base.mkdir(parents=True, exist_ok=True)

    def publicar(**campos: Any) -> None:
        with lock:
            estado.update(campos)

    def registrar(resultado: ResultadoEtapa) -> None:
        with lock:
            resultados.append(resultado)

    def marcar_restantes(indice: int) -> None:
        for restante in list(etapas)[indice:]:
            registrar(
                ResultadoEtapa(
                    chave=restante.chave,
                    titulo=restante.titulo,
                    situacao="nao_executada",
                    segundos=0.0,
                )
            )

    for indice, etapa in enumerate(etapas):
        try:
            _executar_etapa(
                indice,
                etapa,
                login,
                senha,
                escolas,
                stop_event,
                lock,
                estado,
                pasta_base,
                resultados,
                publicar,
                registrar,
                marcar_restantes,
                continuar_event,
            )
        except Exception as exc:  # noqa: BLE001 — nenhuma exceção pode travar a tela
            registrar(
                ResultadoEtapa(
                    chave=etapa.chave,
                    titulo=etapa.titulo,
                    situacao="falhou",
                    segundos=0.0,
                    motivo=str(exc),
                )
            )
            marcar_restantes(indice + 1)
            publicar(interrompida=True, erro_rodada=str(exc))
            break
        if estado.get("interrompida"):
            # Falha ou interrupção: as etapas seguintes já foram marcadas.
            break

    # O pacote completo só existe quando a rodada chegou ao fim sem
    # interrupção nem falha.
    if not estado.get("interrompida") and not estado.get("erro_rodada"):
        destino = montar_pacote(resultados, pasta_base)
        if destino is not None:
            publicar(pacote=(str(destino), destino.name))

    publicar(terminada=True, etapa_atual=None, shared_etapa=None)
