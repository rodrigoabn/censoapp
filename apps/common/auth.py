"""Constantes e trava do MODO LEITURA compartilhadas pelos coletores.

Nenhuma escrita é feita no site do Educacenso. Os 4 `src/auth.py` dos apps
re-exportam este módulo (histórico da Fase 4).
"""

from __future__ import annotations

# URL base do sistema Educacenso.
BASE_URL = "https://educacenso.inep.gov.br"

# Guarda invariante do modo leitura. Qualquer tentativa de escrita no site
# deve ser bloqueada por esta flag.
READ_ONLY = True


def _assert_read_only() -> None:
    if not READ_ONLY:
        raise RuntimeError("MODO LEITURA violado: operações de escrita no site estão proibidas.")
