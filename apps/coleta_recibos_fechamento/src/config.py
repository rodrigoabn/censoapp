"""Configuração da aplicação COLETA DE RECIBOS DE FECHAMENTO do Educacenso.

Compartilha o mesmo fluxo das coletas (login, seleção da escola), porém baixa
o recibo de fechamento (PDF) que o próprio site disponibiliza ao clicar em
"Imprimir". Este dicionário parametriza o frontend e o scraper.
"""

from __future__ import annotations

from .auth import BASE_URL

CONFIG: dict = {
    "key": "fechamento",
    "state_prefix": "rf_",
    "title": "Recibos de Fechamento (1ª Etapa)",
    "subtitle": "Baixa o recibo de fechamento (PDF) de cada escola no Educacenso, "
    "em modo leitura (não altera dados no site).",
    "url": f"{BASE_URL}/fechamento",
    "zip_prefix": "recibos_fechamento",
}
