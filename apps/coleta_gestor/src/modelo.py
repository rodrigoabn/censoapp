"""Mapeamento do template de extração (docs/modelo_coleta_gestor.xlsx).

A aplicação opera em MODO LEITURA: este módulo apenas DESCREVE a estrutura
de destino (nome da aba e rótulos das colunas) para que o scraper saiba
onde gravar cada dado. Nenhuma escrita é feita aqui.
"""

from __future__ import annotations

import openpyxl
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
MODELO_PATH = DOCS_DIR / "modelo_coleta_gestor.xlsx"

# Colunas-chave presentes na aba do modelo.
KEY_COLUMNS = ["Código do Inep", "Unidade Escolar"]

# Nome da aba no modelo.
GESTOR_SHEET = "Vínculo do gestor"


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
    """Retorna {nome_da_aba: [rótulos_da_linha_1...]} para o modelo.

    No modelo do gestor, a linha 1 traz diretamente os rótulos das 6 colunas
    que serão populadas com os dados extraídos (Código do Inep, Unidade
    Escolar, 1 – Cargo, 2 - Critério..., 3 - Situação..., Email principal).
    """
    wb = openpyxl.load_workbook(MODELO_PATH, data_only=True)
    model: dict[str, list[str]] = {}
    for ws in wb.worksheets:
        row1 = [c for c in next(ws.iter_rows(min_row=1, max_row=1, values_only=True))]
        # Remove colunas vazias à direita.
        while row1 and row1[-1] is None:
            row1.pop()
        # .strip() remove também o non-breaking space (\xa0) que às vezes
        # acompanha os rótulos exportados do Excel.
        model[ws.title] = [str(c).strip() if c is not None else "" for c in row1]
    return model


def all_sheets(model: dict[str, list[str]]) -> list[str]:
    """Devolve a lista de abas do modelo que possuem ao menos uma coluna."""
    return [s for s, cols in model.items() if cols]


def sheet_column_index(model: dict[str, list[str]], sheet: str, label: str) -> int | None:
    """Índice (0-based) da coluna cujo rótulo corresponde a `label`, ou None."""
    norm = _normalize(label)
    for idx, col in enumerate(model.get(sheet, [])):
        if _normalize(col) == norm:
            return idx
    return None


def resolve_sheet_name(site_tab: str) -> str:
    """Devolve o nome da aba no modelo a partir do nome usado no scraper."""
    # Há apenas uma aba ("Vínculo do gestor"); mantido para simetria com o
    # padrão do coleta_cadastros_escolas.
    return site_tab or GESTOR_SHEET


# Aliases explícitos: rótulo do site (normalizado) -> rótulo exato da coluna
# no modelo (2ª linha). Usado quando o rótulo do site difere do modelo
# (ex.: ausência do prefixo numérico "1 –", "2 -", "3 -").
_FIELD_ALIASES = {
    "cargo": "1 – Cargo",
    "criteriodeacessoaocargofuncao": "2 - Critério de acesso ao cargo/função",
    "situacaofuncionalregimedecontratacaotipodevinculo":
        "3 - Situação Funcional/Regime de contratação/Tipo de vínculo",
    "emailprincipal": "Email principal",
    "email": "Email principal",
    "gestorescolarcomdeficienciatranstornodoespectroautistaealtashabilidadesousuperdotacao":
        "12 – Gestor(a) escolar com deficiência, transtorno do espectro autista e altas habilidades ou superdotação",
}


def resolve_field_label(norm_label: str) -> str | None:
    """Devolve o rótulo exato do modelo para um rótulo normalizado do site.

    Retorna None se não houver alias explícito.
    """
    return _FIELD_ALIASES.get(norm_label)
