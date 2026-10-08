"""Exportação local dos dados coletados (apenas-leitura no site).

Gera um único arquivo .xlsx com 6 abas (espelho de modelo_coleta.xlsx).
Durante a raspagem, cada escola é appendada em CSVs temporários por aba
(resiliência). Ao final, os CSVs são consolidados no XLSX final.

Nenhuma escrita é feita no site Educacenso (cláusula pétrea de modo leitura).
"""

from __future__ import annotations

import csv
import io
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter

import src.modelo as modelo

TMP_DIR = Path(tempfile.gettempdir()) / "educacenso_tmp"


def _ajustar_larguras(ws, min_width: int = 10, max_width: int = 50, pad: int = 2) -> None:
    for col in ws.columns:
        letter = get_column_letter(col[0].column)
        compr = [len(str(c.value)) for c in col if c.value is not None]
        if not compr:
            ws.column_dimensions[letter].width = min_width
            continue
        ws.column_dimensions[letter].width = min(max(max(compr) + pad, min_width), max_width)


def _file_date() -> str:
    return datetime.now().strftime("%d-%m-%Y")


def output_filename() -> str:
    return f"cadastro_escola_educacenso_{_file_date()}.xlsx"


def _safe_sheet_title(model_title: str) -> str:
    """Excel limita abas a 31 chars e proíbe []:*?/\\."""
    return model_title[:31].replace("/", "-").replace(":", "-").replace("[", "(").replace("]", ")")


def append_school_temp(dados: dict[str, dict], tmp_dir: Path = TMP_DIR) -> None:
    """Append os dados de UMA escola nos CSVs temporários (um por aba)."""
    tmp_dir.mkdir(parents=True, exist_ok=True)
    model = modelo.load_model()
    for sheet, row in dados.items():
        cols = model.get(sheet, [])
        if not cols:
            continue
        path = tmp_dir / f"{_safe_sheet_title(sheet)}.csv"
        new = not path.exists()
        with path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=cols)
            if new:
                writer.writeheader()
            writer.writerow({c: row.get(c, "") for c in cols})


def build_xlsx(tmp_dir: Path = TMP_DIR, model=None) -> bytes:
    """Consolida os CSVs temporários em um único XLSX (6 abas) e retorna bytes.

    Remove os CSVs temporários ao final. O nome do arquivo final é tratado
    pelo chamador (frontend) via output_filename().
    """
    if model is None:
        model = modelo.load_model()

    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # remove aba em branco padrão

    for sheet, cols in model.items():
        title = _safe_sheet_title(sheet)
        path = tmp_dir / f"{title}.csv"
        ws = wb.create_sheet(title=title)
        ws.append(cols)  # cabeçalho = 2ª linha do modelo
        if path.exists():
            with path.open(encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader, None)  # pula cabeçalho do CSV
                for r in reader:
                    ws.append(r)

    for sheet in wb.sheetnames:
        _ajustar_larguras(wb[sheet])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    # Limpeza dos temporários.
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return buffer.getvalue()


def reset_temp(tmp_dir: Path = TMP_DIR) -> None:
    """Remove CSVs temporários de uma execução anterior (início do lote)."""
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)
