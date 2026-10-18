"""Células iniciadas com '=' não devem virar fórmula nos XLSX da verificação."""

from __future__ import annotations

import io

import openpyxl
import pandas as pd

from apps.verificacao_inconsistencias.src import frontend


def _valores(data: bytes) -> list:
    wb = openpyxl.load_workbook(io.BytesIO(data))
    return [c.value for row in wb.active.iter_rows() for c in row]


def test_build_xlsx_neutraliza_formulas():
    data = frontend._build_xlsx(
        [
            {
                "codigo_inep": "111",
                "nome_unidade": "Escola Um",
                "tipo_validacao": "=1+1",
                "detalhes": "=SUM(A1:A9)",
            }
        ],
        modo="padrao",
    )
    valores = _valores(data)
    assert "'=1+1" in valores
    assert "'=SUM(A1:A9)" in valores


def test_unificado_xlsx_neutraliza_formulas_e_mantem_numeros():
    df = pd.DataFrame({"Unidade Escolar": ["=1+1"], "Total": [3]})
    valores = _valores(frontend._unificado_xlsx(df))
    assert "'=1+1" in valores
    assert 3 in valores


def test_duplicadas_e_sem_cpf_neutralizam_formulas():
    dup = frontend._duplicadas_xlsx([
        {
            "codigo_inep": "111",
            "nome_unidade": "Escola Um",
            "identificacao_unica": "=1+1",
            "nome": "Fulano",
            "cpf": "---",
            "motivo": "=cmd",
        },
    ])
    assert "'=1+1" in _valores(dup)
    assert "'=cmd" in _valores(dup)

    sem_cpf = frontend._sem_cpf_xlsx([
        {
            "codigo_inep": "111",
            "nome_unidade": "Escola Um",
            "identificacao_unica": "=1+1",
            "nome": "Fulano",
            "cpf": "=--",
        },
    ])
    assert _valores(sem_cpf).count("'=1+1") >= 1


def test_cor_raca_neutraliza_texto_e_mantem_numeros():
    data = frontend._levantamento_cor_raca_xlsx([
        {"codigo_inep": "111", "nome_unidade": "=1+1", "preta": 2},
    ])
    valores = _valores(data)
    assert "'=1+1" in valores
    assert 2 in valores
