"""Conftest raiz da suíte.

Seções:

1. Fixtures compartilhadas dos testes golden das regras de verificação
   (Fase 3): `wb_bytes` e `df`.

Convenções dos goldens:

- Constantes e cabeçalhos vêm **sempre** dos módulos de produção
  (`apps/*/src/rules/*` ou equivalentes), referenciados uma única vez no molde
  de cada arquivo de teste — nunca redigitados nos casos.
- Valores de célula são gravados como texto, como nos XLSX exportados do
  portal; números viram `str()` dentro das regras (`_val`).
- Cada aba do molde tem pelo menos uma linha de dados: aba vazia interrompe a
  validação (early-return) e deixaria as regras seguintes sem exercício.
- Nomes de aba no XLSX têm no máximo 31 caracteres (limite do formato).
"""

from __future__ import annotations

import io

import openpyxl
import pandas as pd
import pytest


@pytest.fixture
def wb_bytes():
    """Fábrica de XLSX em memória: ``wb_bytes({aba: [linhas...]})``.

    A primeira linha de cada aba é o cabeçalho; as demais, dados. A ordem do
    dicionário define a ordem das abas no arquivo.
    """

    def _build(sheets: dict[str, list[list]]) -> bytes:
        wb = openpyxl.Workbook()
        for position, (name, rows) in enumerate(sheets.items()):
            assert len(name) <= 31, f"nome de aba acima de 31 chars: {name!r}"
            ws = wb.active if position == 0 else wb.create_sheet()
            ws.title = name
            for row in rows:
                ws.append(list(row))
        buffer = io.BytesIO()
        wb.save(buffer)
        return buffer.getvalue()

    return _build


@pytest.fixture
def df():
    """Fábrica de DataFrame: ``df({coluna: [valores]})`` ou lista de registros."""

    def _build(rows) -> pd.DataFrame:
        return pd.DataFrame(rows)

    return _build
