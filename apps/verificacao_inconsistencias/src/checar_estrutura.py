from __future__ import annotations

import io

import openpyxl


def _load_structure(file_bytes: bytes) -> dict[str, list[str]]:
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    structure: dict[str, list[str]] = {}
    for ws in wb.worksheets:
        row = [c for c in next(ws.iter_rows(min_row=1, max_row=1, values_only=True))]
        while row and row[-1] is None:
            row.pop()
        structure[ws.title] = [str(c) if c is not None else "" for c in row]
    return structure


def checar_estrutura(upload_bytes: bytes, referencia_bytes: bytes) -> tuple[bool, list[str]]:
    erros: list[str] = []

    try:
        ref = _load_structure(referencia_bytes)
    except Exception as exc:
        return False, [f"Não foi possível ler o arquivo de referência: {exc}"]

    try:
        upl = _load_structure(upload_bytes)
    except Exception as exc:
        return False, [f"Não foi possível ler o arquivo enviado: {exc}"]

    abas_ref = set(ref.keys())
    abas_upl = set(upl.keys())

    abas_faltando = abas_ref - abas_upl
    abas_extras = abas_upl - abas_ref

    if abas_faltando:
        erros.append(f"Abas faltando no arquivo: {sorted(abas_faltando)}")
    if abas_extras:
        erros.append(f"Abas não esperadas no arquivo: {sorted(abas_extras)}")

    for aba in sorted(abas_ref & abas_upl):
        cols_ref = ref[aba]
        cols_upl = upl[aba]

        if cols_ref == cols_upl:
            continue

        erros.append(
            f"Aba '{aba}': colunas divergem do esperado. "
            f"Esperado {len(cols_ref)} coluna(s), "
            f"encontrado {len(cols_upl)} coluna(s)."
        )
        for i in range(max(len(cols_ref), len(cols_upl))):
            if i < len(cols_ref) and i < len(cols_upl):
                if cols_ref[i] != cols_upl[i]:
                    erros.append(
                        f"  Coluna {i+1}: esperado '{cols_ref[i]}', "
                        f"encontrado '{cols_upl[i]}'"
                    )
            elif i < len(cols_ref):
                erros.append(f"  Coluna {i+1}: esperado '{cols_ref[i]}' — faltando")
            else:
                erros.append(f"  Coluna {i+1}: extra '{cols_upl[i]}'")

    return (len(erros) == 0), erros
