"""A rodada da Coleta Automática: as etapas, uma após a outra, em background.

A thread **não** toca em `st.*`; ela publica o que está acontecendo no
dicionário `estado` (protegido por `lock`), que a tela lê a cada rerun.

Regras da rodada:

- as etapas rodam **em sequência**, na ordem do registro;
- erro do worker ⇒ a etapa é "falhou" e a **rodada para**;
- etapa que rodou sem erro mas **não coletou nenhuma escola** ⇒ a rodada
  **pausa** e pergunta ao usuário se deve continuar;
- o usuário pode interromper a rodada a qualquer momento (o `stop_check` do
  coletor encerra a etapa em andamento com segurança).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from apps.common.export import build_pending_xlsx, remover_temp

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
        # Interrupção pedida antes de começar esta etapa.
        if stop_event.is_set():
            marcar_restantes(indice)
            publicar(interrompida=True)
            break

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
        }
        publicar(etapa_atual=etapa.chave, shared_etapa=shared, aguardando=None)

        t0 = time.monotonic()
        etapa.worker(
            etapa.config, login, senha, escolas, stop_event, lock, shared, pasta_etapa
        )
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
            publicar(interrompida=True, etapa_atual=None, shared_etapa=None)
            break

        # Rodou sem erro, mas não coletou nenhuma escola: a rodada pausa e
        # pergunta ao usuário se deve continuar.
        if not shared.get("count", 0):
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
                publicar(interrompida=True, etapa_atual=None, shared_etapa=None)
                break
            publicar(aguardando=None)
            remover_temp(pasta_etapa)
            continue

        # Etapa concluída: monta o artefato (e a planilha de pendências).
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
                situacao="concluida",
                segundos=segundos,
                caminho_artefato=str(caminho_artefato),
                caminho_pendencias=str(caminho_pendencias) if caminho_pendencias else None,
            )
        )
        remover_temp(pasta_etapa)

    publicar(etapa_atual=None, shared_etapa=None)
