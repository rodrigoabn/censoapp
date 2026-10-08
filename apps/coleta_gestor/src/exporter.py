"""Exportação local dos dados coletados (apenas-leitura no site).

Gera um único arquivo .xlsx com a aba "Vínculo do gestor" (espelho de
modelo_coleta_gestor.xlsx). Durante a raspagem, cada escola é appendada em
um CSV temporário; ao final, o CSV é consolidado no XLSX final.

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

from . import modelo

TMP_DIR = Path(tempfile.gettempdir()) / "educacenso_gestor_tmp"
SHEET = modelo.GESTOR_SHEET


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
    return f"vinculo_gestor_educacenso_{_file_date()}.xlsx"


def _sheet_file(sheet: str) -> str:
    """Nome de arquivo seguro para a aba (mantém legível, sem caracteres inválidos)."""
    name = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in sheet)
    return f"{name}.csv"


def append_school_temp(dados: dict[str, dict], tmp_dir: Path = TMP_DIR) -> None:
    """Append os dados de UMA escola em um CSV temporário por aba do modelo.

    `dados` é {nome_da_aba: {coluna: valor}}.
    """
    tmp_dir.mkdir(parents=True, exist_ok=True)
    model = modelo.load_model()
    for sheet, cols in model.items():
        if not cols:
            continue
        row = dados.get(sheet, {c: "" for c in cols})
        path = tmp_dir / _sheet_file(sheet)
        new = not path.exists()
        with path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=cols)
            if new:
                writer.writeheader()
            writer.writerow({c: row.get(c, "") for c in cols})


def build_xlsx(tmp_dir: Path = TMP_DIR, model=None) -> bytes:
    """Consolida os CSVs temporários em um único XLSX (todas as abas do modelo)
    e retorna os bytes. Remove os CSVs temporários ao final.
    """
    if model is None:
        model = modelo.load_model()

    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # remove aba em branco padrão

    for sheet, cols in model.items():
        if not cols:
            continue
        ws = wb.create_sheet(title=sheet)
        ws.append(cols)  # cabeçalho = 1ª linha do modelo
        path = tmp_dir / _sheet_file(sheet)
        if path.exists():
            with path.open(encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader, None)  # pula cabeçalho do CSV
                for r in reader:
                    ws.append(r)

    for sheet in wb.sheetnames:
        _ajustar_larguras(wb[sheet])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    if tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return buffer.getvalue()


def reset_temp(tmp_dir: Path = TMP_DIR) -> None:
    """Remove CSVs temporários de uma execução anterior (início do lote)."""
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)
