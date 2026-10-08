"""Mapeamento do template de extração (docs/modelo_coleta.xlsx).

A aplicação opera em MODO LEITURA: este módulo apenas DESCREVE a estrutura
de destino (nomes das abas e rótulos das colunas) para que o scraper saiba
onde gravar cada dado na Planilha Google. Nenhuma escrita é feita aqui.
"""

from __future__ import annotations

import openpyxl
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
MODELO_PATH = DOCS_DIR / "modelo_coleta.xlsx"

# Colunas-chave presentes em todas as abas do modelo.
KEY_COLUMNS = ["Código do Inep", "Unidade Escolar"]


def _normalize(label: str) -> str:
    """Normaliza rótulo para comparação tolerante (minúsculo, sem acento/espaço)."""
    if label is None:
        return ""
    repl = {
        "á": "a", "à": "a", "ã": "a", "â": "a", "ä": "a",
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "í": "i", "ì": "i", "î": "i", "ï": "i",
        "ó": "o", "ò": "o", "õ": "o", "ô": "o", "ö": "o",
        "ú": "u", "ù": "u", "û": "u", "ü": "u",
        "ç": "c", "ñ": "n",
    }
    s = str(label).lower()
    for k, v in repl.items():
        s = s.replace(k, v)
    return "".join(ch for ch in s if ch.isalnum())


def load_model() -> dict[str, list[str]]:
    """Retorna {nome_da_aba: [rótulos_da_linha_2...]} para cada aba do modelo.

    A linha 1 do modelo agrupa perguntas (cabeçalho); a linha 2 traz os
    rótulos efetivos das colunas que serão populadas com os dados extraídos.
    """
    wb = openpyxl.load_workbook(MODELO_PATH, data_only=True)
    model: dict[str, list[str]] = {}
    for ws in wb.worksheets:
        row2 = [c for c in next(ws.iter_rows(min_row=2, max_row=2, values_only=True))]
        # Remove colunas vazias à direita.
        while row2 and row2[-1] is None:
            row2.pop()
        model[ws.title] = [str(c) if c is not None else "" for c in row2]
    return model


def sheet_column_index(model: dict[str, list[str]], sheet: str, label: str) -> int | None:
    """Índice (0-based) da coluna cujo rótulo corresponde a `label`, ou None."""
    norm = _normalize(label)
    for idx, col in enumerate(model.get(sheet, [])):
        if _normalize(col) == norm:
            return idx
    return None


# Mapeia o nome exato da aba no site (Educacenso) para o nome da aba no
# template modelo_coleta.xlsx (que pode estar truncado).
_TAB_ALIASES = {
    "Vinculação institucional e Convênio": "Vinculação institucional e Conv",
    "Equipamentos e recursos tecnológicos": "Equipamentos e recursos tecnoló",
}


def resolve_sheet_name(site_tab: str) -> str:
    """Devolve o nome da aba no modelo a partir do nome da aba no site."""
    return _TAB_ALIASES.get(site_tab, site_tab)


# Aliases explícitos: rótulo do site (normalizado) -> rótulo exato da coluna
# no modelo (2ª linha). Usado quando o site acrescenta palavras ("da escola")
# ou usa camelCase em relação ao modelo.
_FIELD_ALIASES = {
    "3localizacaozonadaescola": "3 – localizacaoZona",
}


def resolve_field_label(norm_label: str) -> str | None:
    """Devolve o rótulo exato do modelo para um rótulo normalizado do site.

    Retorna None se não houver alias explícito.
    """
    return _FIELD_ALIASES.get(norm_label)
