"""Leitura da lista de escolas enviada pelo usuário (.xlsx / .xls).

O arquivo deve conter as colunas:
    - "código do inep"
    - "nome da unidade"

A leitura é feita em MODO LEITURA (apenas leitura local do arquivo).

Módulo comum da Fase 4: os 4 coletores usavam cópias idênticas deste módulo;
a verificação de inconsistências consome com `require_nome=False` e aliases
próprios (inclui "unidade escolar").
"""

from __future__ import annotations

import io

import pandas as pd


def _find_column(columns, wanted: str) -> str | None:
    wanted = wanted.lower().strip()
    for col in columns:
        if str(col).lower().strip() == wanted:
            return col
    # Tolerância parcial.
    for col in columns:
        if wanted in str(col).lower().strip():
            return col
    return None


def read_school_list(
    uploaded_file,
    *,
    require_nome: bool = True,
    nome_aliases: tuple[str, ...] = ("nome da unidade", "nome da unidade escolar"),
) -> list[dict]:
    """Recebe um uploaded file do Streamlit e devolve lista de
    {'codigo_inep': str, 'nome_unidade': str}.

    Levanta ValueError se as colunas obrigatórias não estiverem presentes.
    Com ``require_nome=False`` a ausência da coluna de nome é tolerada
    (nome vira ""), como faz a verificação de inconsistências.
    """
    raw = uploaded_file.read()
    # xlrd só lê .xls legados; openpyxl cobre .xlsx. pandas deduz o engine.
    df = pd.read_excel(io.BytesIO(raw), dtype=str)

    col_codigo = _find_column(df.columns, "código do inep") or _find_column(df.columns, "codigo do inep")
    col_nome = None
    for alias in nome_aliases:
        col_nome = _find_column(df.columns, alias)
        if col_nome is not None:
            break

    if col_codigo is None:
        raise ValueError(
            "Coluna 'código do inep' não encontrada no arquivo. "
            f"Colunas presentes: {list(df.columns)}"
        )
    if col_nome is None and require_nome:
        raise ValueError(
            "Coluna 'nome da unidade' não encontrada no arquivo. "
            f"Colunas presentes: {list(df.columns)}"
        )

    escolas: list[dict] = []
    for _, row in df.iterrows():
        codigo = str(row[col_codigo]).strip()
        if codigo.lower() in ("nan", "none", ""):
            continue
        nome = str(row[col_nome]).strip() if col_nome else ""
        if nome.lower() in ("nan", "none"):
            nome = ""
        escolas.append({"codigo_inep": codigo, "nome_unidade": nome})
    return escolas
