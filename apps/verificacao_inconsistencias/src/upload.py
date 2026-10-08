from __future__ import annotations

import io
import os
import zipfile

import pandas as pd


def _find_column(columns, wanted: str) -> str | None:
    wanted = wanted.lower().strip()
    for col in columns:
        if str(col).lower().strip() == wanted:
            return col
    for col in columns:
        if wanted in str(col).lower().strip():
            return col
    return None


def read_school_list(uploaded_file) -> list[dict]:
    raw = uploaded_file.read()
    df = pd.read_excel(io.BytesIO(raw), dtype=str)

    col_codigo = _find_column(df.columns, "código do inep") or _find_column(df.columns, "codigo do inep")
    col_nome = (
        _find_column(df.columns, "nome da unidade")
        or _find_column(df.columns, "nome da unidade escolar")
        or _find_column(df.columns, "unidade escolar")
    )

    if col_codigo is None:
        raise ValueError(
            "Coluna 'código do inep' não encontrada no arquivo. "
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


def _extrair_codigo_nome(filename: str) -> tuple[str, str]:
    basename = os.path.splitext(os.path.basename(filename))[0]
    parts = basename.split("_", 1)
    codigo = parts[0]
    nome = parts[1] if len(parts) > 1 else ""
    return codigo, nome


def _eh_linha_titulo(linha: str) -> bool:
    """Retorna True se a linha parece ser um título agrupado, sem valores a cabeçalho."""
    cells = linha.split(";")
    preenchidas = sum(1 for c in cells if str(c).strip())
    return preenchidas <= 3


_COLUNAS_INTERNAS = {"Código do Inep", "Nome da Unidade"}


def checar_colunas(df: pd.DataFrame, esperadas: list[str]) -> tuple[bool, list[str], list[str]]:
    """Compara as colunas naturais do DataFrame com a lista esperada.

    Retorna (corresponde, faltando, nao_esperadas). Colunas internas
    (Código do Inep/Nome da Unidade) são ignoradas na comparação.
    """
    reais = [c for c in df.columns if c not in _COLUNAS_INTERNAS]
    faltando = [c for c in esperadas if c not in reais]
    extras = [c for c in reais if c not in esperadas]
    return (not faltando and not extras), faltando, extras


def read_zip_merged(raw_bytes: bytes) -> dict:
    zf = zipfile.ZipFile(io.BytesIO(raw_bytes))

    csv_count = 0
    frames: list[pd.DataFrame] = []

    for info in zf.infolist():
        if not info.filename.endswith(".csv"):
            continue
        csv_count += 1
        content = zf.read(info.filename)
        primeira_linha = content.decode("utf-8-sig", errors="replace").split("\n", 1)[0]
        skiprows = 1 if _eh_linha_titulo(primeira_linha) else 0
        df = pd.read_csv(
            io.BytesIO(content),
            delimiter=";",
            encoding="utf-8-sig",
            dtype=str,
            skiprows=skiprows,
        )
        codigo, nome = _extrair_codigo_nome(info.filename)
        df["Código do Inep"] = codigo
        df["Nome da Unidade"] = nome
        frames.append(df)

    if not frames:
        raise ValueError("Nenhum arquivo CSV encontrado dentro do ZIP.")

    merged = pd.concat(frames, ignore_index=True)

    primeiras = ["Código do Inep", "Nome da Unidade"]
    demais = [c for c in merged.columns if c not in _COLUNAS_INTERNAS]
    merged = merged[primeiras + demais]

    escolas = merged[["Código do Inep", "Nome da Unidade"]].drop_duplicates().to_dict("records")

    return {
        "unificado": merged,
        "escolas": escolas,
        "csv_count": csv_count,
    }


def read_turmas_zip(raw_bytes: bytes) -> dict:
    dados = read_zip_merged(raw_bytes)
    merged = dados["unificado"]

    tipo_col = "Tipo de turma"
    if tipo_col not in merged.columns:
        raise ValueError(
            f"Coluna '{tipo_col}' não encontrada nos CSVs. "
            f"Colunas presentes: {list(merged.columns)}"
        )

    etapa_col = "Etapa Agregada"
    eh_aee = (merged[etapa_col] == "-") & (merged[tipo_col] == "Atendimento educacional especializado (AEE)")
    eh_atv = (merged[etapa_col] == "-") & (merged[tipo_col] == "Atividade complementar")

    df_aee = merged[eh_aee].copy()
    df_atv = merged[eh_atv].copy()
    df_curricular = merged[merged[tipo_col] == "Curricular (etapa de ensino)"].copy()
    df_escolarizacao = merged[~(eh_aee | eh_atv)].copy()
    df_escolarizacao["periodo_turma"] = df_escolarizacao["Nome da turma"].astype(str).str[:2]
    df_escolarizacao["verifica_integral"] = df_escolarizacao["Nome da turma"].astype(str).str[2:3]

    return {
        "unificado": merged,
        "turmas_aee": df_aee,
        "turmas_atvcomplementar": df_atv,
        "turmas_curricular": df_curricular,
        "turmas_escolarizacao": df_escolarizacao,
        "escolas": dados["escolas"],
        "csv_count": dados["csv_count"],
    }


def read_profissionais_zip(raw_bytes: bytes) -> dict:
    dados = read_zip_merged(raw_bytes)
    merged = dados["unificado"]

    etapa_col = "Etapa de ensino"
    if etapa_col not in merged.columns:
        raise ValueError(
            f"Coluna '{etapa_col}' não encontrada nos CSVs. "
            f"Colunas presentes: {list(merged.columns)}"
        )

    eh_aee_atv = merged[etapa_col] == "Não se aplica"

    return {
        "unificado": merged,
        "prof_aee_atv": merged[eh_aee_atv].copy(),
        "prof_curricular": merged[~eh_aee_atv].copy(),
        "escolas": dados["escolas"],
        "csv_count": dados["csv_count"],
    }


def read_aluno_zip(raw_bytes: bytes) -> dict:
    dados = read_zip_merged(raw_bytes)
    merged = dados["unificado"]

    etapa_col = "Etapa de ensino"
    aee_col = "Tipo de atendimento educacional especializado (AEE)"
    transp_col = "Transporte escolar (Sim/Não)"
    def_col = "Tipo(s) de deficiência(s), transtorno(s) do espectro autista e altas habilidades ou superdotação"
    transt_col = "Tipo(s) de transtorno(s) que impacta(m) o desenvolvimento da aprendizagem"
    for col in (etapa_col, aee_col, transp_col, def_col, transt_col):
        if col not in merged.columns:
            raise ValueError(
                f"Coluna '{col}' não encontrada nos CSVs. "
                f"Colunas presentes: {list(merged.columns)}"
            )

    na = merged[etapa_col] == "Não se aplica"
    eh_aee = na & (merged[aee_col] != "--")
    eh_atv = na & (merged[aee_col] == "--")
    eh_transporte = merged[transp_col] == "Sim"
    eh_deficiencia = ((merged[def_col] != "--") | (merged[transt_col] != "--")) & ~na

    return {
        "unificado": merged,
        "aluno_curricular": merged[~(eh_aee | eh_atv)].copy(),
        "aluno_aee": merged[eh_aee].copy(),
        "aluno_atv": merged[eh_atv].copy(),
        "aluno_transporte": merged[eh_transporte].copy(),
        "aluno_deficiencia": merged[eh_deficiencia].copy(),
        "escolas": dados["escolas"],
        "csv_count": dados["csv_count"],
    }
