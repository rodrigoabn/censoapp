"""Armazenamento temporário dos PDF coletados e geração do ZIP final.

Durante a coleta, o recibo (PDF) baixado de cada escola é gravado em uma pasta
temporária (resiliência). Ao final, todos os PDF são compactados em um único
arquivo ZIP disponibilizado para download.

Nenhuma escrita é feita no site Educacenso (cláusula pétrea de modo leitura).
"""

from __future__ import annotations

import io
import re
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter

TMP_DIR = Path(tempfile.gettempdir()) / "educacenso_recibos_fechamento_tmp"


def _file_date() -> str:
    return datetime.now().strftime("%d-%m-%Y")


def output_filename(prefix: str) -> str:
    return f"{prefix}_{_file_date()}.zip"


def pending_filename(prefix: str) -> str:
    return f"{prefix}_escolas_nao_coletadas_{_file_date()}.xlsx"


def build_pending_xlsx(failures: list[dict]) -> bytes:
    """Gera um XLSX com as escolas processadas que não tiveram recibo coletado.

    Colunas: Código do Inep | Nome da Unidade | Motivo.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Escolas não coletadas"
    ws.append(["Código do Inep", "Nome da Unidade", "Motivo"])
    for f in failures:
        ws.append([
            f.get("codigo_inep", ""),
            f.get("nome_unidade", ""),
            f.get("motivo", ""),
        ])

    _ajustar_larguras(ws)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def _ajustar_larguras(ws, min_width: int = 10, max_width: int = 50, pad: int = 2) -> None:
    for col in ws.columns:
        letter = get_column_letter(col[0].column)
        compr = [len(str(c.value)) for c in col if c.value is not None]
        if not compr:
            ws.column_dimensions[letter].width = min_width
            continue
        ws.column_dimensions[letter].width = min(max(max(compr) + pad, min_width), max_width)


def _safe_name(name: str) -> str:
    """Sanitiza o nome de arquivo (remove caracteres inválidos)."""
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name or "").strip()
    return name[:120] if name else "escola"


def pdf_filename(codigo: str, nome: str) -> str:
    codigo = _safe_name(codigo)
    nome = _safe_name(nome)
    return f"{codigo}_{nome}.pdf" if nome else f"{codigo}.pdf"


def reset_temp(tmp_dir: Path = TMP_DIR) -> None:
    """Remove PDFs temporários de uma execução anterior (início do lote)."""
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)


def append_pdf(codigo: str, nome: str, data: bytes, tmp_dir: Path = TMP_DIR) -> None:
    """Grava o PDF de UMA escola na pasta temporária."""
    tmp_dir.mkdir(parents=True, exist_ok=True)
    path = tmp_dir / pdf_filename(codigo, nome)
    # Evita sobrescrever caso haja código repetido.
    if path.exists():
        stem, suffix = path.stem, path.suffix
        i = 2
        while (tmp_dir / f"{stem}_{i}{suffix}").exists():
            i += 1
        path = tmp_dir / f"{stem}_{i}{suffix}"
    path.write_bytes(data)


def count_temp(tmp_dir: Path = TMP_DIR) -> int:
    if not tmp_dir.exists():
        return 0
    return sum(1 for _ in tmp_dir.glob("*.pdf"))


def build_zip(tmp_dir: Path = TMP_DIR) -> bytes:
    """Compacta todos os PDF temporários em um ZIP e retorna os bytes.

    Remove os PDFs temporários ao final.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        if tmp_dir.exists():
            for pdf_path in sorted(tmp_dir.glob("*.pdf")):
                zf.write(pdf_path, arcname=pdf_path.name)
    buffer.seek(0)

    if tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return buffer.getvalue()
