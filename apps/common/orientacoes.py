"""Card de "Orientações de uso" — layout único em todas as aplicações do HUB.

Todas as telas (coleta, adequação, verificação e unificador) exibem as
orientações na coluna direita, ao lado do formulário principal, com o mesmo
título e a mesma estrutura de card. Este módulo concentra o componente para
que uma alteração de estilo valha para o site inteiro.
"""

from __future__ import annotations

from typing import Any

# Proporção das colunas: conteúdo principal à esquerda, orientações à direita.
COLS_ORIENTACOES = [1.4, 1]

TITULO_ORIENTACOES = "Orientações de uso"


def card_orientacoes(st_mod: Any, corpo: str, aviso: str = "") -> None:
    """Renderiza o card de orientações (coluna direita) de forma padronizada.

    ``corpo`` — markdown com a lista de passos/instruções.
    ``aviso`` — bloco HTML opcional (badge + texto de atenção) exibido
    entre o título e a lista.
    """
    st_mod.markdown('<div class="custom-card">', unsafe_allow_html=True)
    cabecalho = f"<h3>{TITULO_ORIENTACOES}</h3>"
    if aviso:
        cabecalho += f"\n{aviso}"
    st_mod.markdown(cabecalho, unsafe_allow_html=True)
    st_mod.markdown(corpo, unsafe_allow_html=True)
    st_mod.markdown('</div>', unsafe_allow_html=True)
