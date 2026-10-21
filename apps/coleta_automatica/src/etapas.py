"""Registro das 6 etapas da Coleta Automática.

Cada etapa reusa, **sem alterar**, o `config`, o worker e o
exporter/zipper do coletor de origem — a rodada da Coleta Automática apenas
os executa em sequência.

O `_ctx()` dos apps é privado por herança da Fase 4; importá-lo aqui, em vez
de tocar nos 6 coletores, foi escolha deliberada (o design proíbe alterá-los).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from apps.coleta_cadastros_escolas.src import frontend as _cadastros
from apps.coleta_gestor.src import frontend as _gestor
from apps.coleta_recibos_fechamento.src import frontend as _recibos
from apps.coleta_relatorios.src import frontend as _relatorios
from apps.coleta_relatorios.src.reports import REPORTS


@dataclass(frozen=True)
class Etapa:
    """Uma etapa da rodada: um coletor do HUB, pronto para ser executado.

    ``chave`` identifica a etapa; ``pasta`` é o nome da pasta dela dentro do
    ZIP final; ``config`` é o config do app de origem; ``zipper`` é o módulo
    que monta o artefato; ``worker`` é a thread de coleta (assinatura
    "config primeiro"); ``textos`` são os textos do app.
    """

    chave: str
    titulo: str
    pasta: str
    config: dict
    zipper: Any
    worker: Callable
    textos: Any


def _etapa(chave: str, titulo: str, pasta: str, config: dict, modulo: Any) -> Etapa:
    """Monta uma etapa a partir do ``_ctx()`` do app de origem."""
    ctx = modulo._ctx()
    return Etapa(
        chave=chave,
        titulo=titulo,
        pasta=pasta,
        config=config,
        zipper=ctx.zipper,
        worker=ctx.scrape_worker,
        textos=ctx.textos,
    )


#: As 6 etapas, na ordem em que a rodada as executa.
ETAPAS: tuple[Etapa, ...] = (
    _etapa(
        "cadastros_escolas",
        "Cadastros das escolas",
        "cadastros_escolas",
        _cadastros.CONFIG,
        _cadastros,
    ),
    _etapa(
        "gestor",
        "Cadastro do gestor",
        "gestor",
        _gestor.CONFIG,
        _gestor,
    ),
    _etapa(
        "relatorios_turmas",
        "Relatórios de Turmas",
        "relatorios_turmas",
        REPORTS["turmas"],
        _relatorios,
    ),
    _etapa(
        "relatorios_alunos",
        "Relatórios de Alunos",
        "relatorios_alunos",
        REPORTS["alunos"],
        _relatorios,
    ),
    _etapa(
        "relatorios_profissionais",
        "Relatórios de Profissionais Escolares",
        "relatorios_profissionais",
        REPORTS["profissionais"],
        _relatorios,
    ),
    _etapa(
        "recibos",
        "Recibos de Fechamento",
        "recibos",
        _recibos.CONFIG,
        _recibos,
    ),
)


def etapa_por_chave(chave: str) -> Etapa:
    """Devolve a etapa de uma chave; levanta ``KeyError`` se não existir."""
    for etapa in ETAPAS:
        if etapa.chave == chave:
            return etapa
    raise KeyError(chave)
