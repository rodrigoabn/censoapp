"""Módulos compartilhados pelos apps do HUB (Fase 4).

Concentra o que era duplicado entre os coletores: autenticação/MODO LEITURA,
leitura da lista de escolas, browser/sessão Playwright, laço de coleta,
exportação (tmp/ZIP/XLSX) e blocos de UI.

Regra da fase: cada módulo de app mantém os nomes antigos como
aliases/wrappers finos — os monkeypatches dos testes continuam valendo.
"""

from __future__ import annotations
