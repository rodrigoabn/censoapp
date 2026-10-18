"""Utilidades de sessão do HUB (app.py)."""

from __future__ import annotations

import threading


def liberar_execucoes(estado) -> int:
    """Sinaliza parada de toda execução em andamento antes de limpar o estado.

    Percorre os valores de `estado` e chama `.set()` em cada `threading.Event`
    (ex.: flags `*_stop` das coletas). Não remove chaves — a limpeza continua
    acontecendo em `app.py`. Retorna quantos eventos foram sinalizados.
    """
    total = 0
    for valor in list(estado.values()):
        if isinstance(valor, threading.Event):
            valor.set()
            total += 1
    return total
