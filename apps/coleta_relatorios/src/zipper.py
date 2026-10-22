"""Armazenamento temporário dos CSV coletados e geração do ZIP final.

Durante a coleta, o CSV baixado de cada escola é gravado em uma pasta
temporária (resiliência). Ao final, todos os CSV são compactados em um único
arquivo ZIP disponibilizado para download.

Nenhuma escrita é feita no site Educacenso (cláusula pétrea de modo leitura).
"""

from __future__ import annotations

from pathlib import Path

from apps.common import export as _export

_TMP_PREFIX = "educacenso_relatorios_tmp_"


def nova_pasta_temporaria() -> Path:
    """Wrapper de `apps.common.export` (histórico): pasta exclusiva da execução."""
    return _export.nova_pasta_temporaria(_TMP_PREFIX)


remover_temp = _export.remover_temp
_file_date = _export._file_date


def output_filename(prefix: str) -> str:
    """Wrapper de `apps.common.export` (histórico): nome com o qualificador do app."""
    return _export.output_filename(prefix, qualificador="educacenso")


pending_filename = _export.pending_filename
_neutralizar_formulas = _export._neutralizar_formulas
_ajustar_larguras = _export._ajustar_larguras
_safe_name = _export._safe_name
build_pending_xlsx = _export.build_pending_xlsx


def append_csv(codigo: str, nome: str, data: bytes, tmp_dir: Path) -> None:
    """Wrapper de `apps.common.export` (histórico)."""
    return _export.append_arquivo(codigo, nome, data, tmp_dir, ".csv")


def count_temp(tmp_dir: Path) -> int:
    """Wrapper de `apps.common.export` (histórico)."""
    return _export.count_temp(tmp_dir, ".csv")


def build_zip(tmp_dir: Path) -> bytes:
    """Wrapper de `apps.common.export` (histórico)."""
    return _export.build_zip(tmp_dir, ".csv")
