from __future__ import annotations

import zipfile
import io

import pandas as pd


def read_zip_csvs(raw_bytes: bytes) -> dict[str, pd.DataFrame]:
    """Lê um ZIP e retorna um dict {filename: DataFrame} com os CSVs encontrados.

    O ZIP deve conter arquivos CSV separados por ponto e vírgula (;)
    com encoding UTF-8-sig (padrão do Educacenso).
    """
    zf = zipfile.ZipFile(io.BytesIO(raw_bytes))
    csvs: dict[str, pd.DataFrame] = {}
    for info in zf.infolist():
        if not info.filename.endswith(".csv"):
            continue
        content = zf.read(info.filename)
        df = pd.read_csv(
            io.BytesIO(content),
            delimiter=";",
            encoding="utf-8-sig",
            dtype=str,
        )
        basename = info.filename
        csvs[basename] = df
    return csvs


def write_zip_from_dataframes(
    dataframes: dict[str, pd.DataFrame],
    nomes_arquivos: list[str] | None = None,
) -> bytes:
    """Cria um arquivo ZIP a partir de um dict {nome: DataFrame}.

    Se ``nomes_arquivos`` for informado, apenas os arquivos listados serão
    incluídos (mantendo a ordem). Caso contrário, todos os dicionários são
    gravados.
    """
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        for nome, df in dataframes.items():
            if nomes_arquivos is not None and nome not in nomes_arquivos:
                continue
            csv_bytes = df.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8")
            zf.writestr(nome, csv_bytes)
    output.seek(0)
    return output.read()