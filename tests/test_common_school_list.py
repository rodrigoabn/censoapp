"""Testes do módulo comum de leitura da lista de escolas — Fase 4.2."""

from __future__ import annotations

import io

import pytest

from apps.common.school_list import _find_column, read_school_list

# ───────────────────────── _find_column ─────────────────────────


@pytest.mark.parametrize(
    ("colunas", "procurada", "esperado"),
    [
        (["código do inep", "nome da unidade"], "código do inep", "código do inep"),
        (["CÓDIGO DO INEP"], "código do inep", "CÓDIGO DO INEP"),
        ([" nome da unidade "], "nome da unidade", " nome da unidade "),
        (["nome da unidade escolar"], "nome da unidade", "nome da unidade escolar"),
        # Igualdade tem prioridade sobre a tolerância parcial.
        (["codigo do inep extra", "codigo do inep"], "codigo do inep", "codigo do inep"),
        (["outra coluna"], "código do inep", None),
    ],
)
def test_find_column(colunas, procurada, esperado):
    assert _find_column(colunas, procurada) == esperado


# ─────────────── read_school_list — modo coletor ────────────────


def test_read_school_list_basico(wb_bytes):
    data = wb_bytes({"Escolas": [
        ["Código do Inep", "Nome da Unidade"],
        ["123", "Escola A"],
        ["456", "Escola B"],
    ]})
    assert read_school_list(io.BytesIO(data)) == [
        {"codigo_inep": "123", "nome_unidade": "Escola A"},
        {"codigo_inep": "456", "nome_unidade": "Escola B"},
    ]


def test_read_school_list_aceita_codigo_sem_acento(wb_bytes):
    data = wb_bytes({"Escolas": [
        ["codigo do inep", "nome da unidade"],
        ["123", "Escola A"],
    ]})
    assert read_school_list(io.BytesIO(data)) == [
        {"codigo_inep": "123", "nome_unidade": "Escola A"},
    ]


def test_read_school_list_ignora_linhas_sem_codigo(wb_bytes):
    data = wb_bytes({"Escolas": [
        ["Código do Inep", "Nome da Unidade"],
        ["", "Escola sem código"],
        ["nan", "Placeholder nan"],
        ["none", "Placeholder none"],
        ["123", "Escola A"],
    ]})
    assert read_school_list(io.BytesIO(data)) == [
        {"codigo_inep": "123", "nome_unidade": "Escola A"},
    ]


def test_read_school_list_nome_vazio_vira_string_vazia(wb_bytes):
    data = wb_bytes({"Escolas": [
        ["Código do Inep", "Nome da Unidade"],
        ["123", ""],
    ]})
    assert read_school_list(io.BytesIO(data)) == [
        {"codigo_inep": "123", "nome_unidade": ""},
    ]


def test_read_school_list_exige_nome_por_padrao(wb_bytes):
    data = wb_bytes({"Escolas": [["Código do Inep"], ["123"]]})
    with pytest.raises(ValueError) as excinfo:
        read_school_list(io.BytesIO(data))
    assert str(excinfo.value).startswith("Coluna 'nome da unidade' não encontrada no arquivo.")


def test_read_school_list_erro_sem_coluna_codigo(wb_bytes):
    data = wb_bytes({"Escolas": [["Nome da Unidade"], ["Escola A"]]})
    with pytest.raises(ValueError) as excinfo:
        read_school_list(io.BytesIO(data))
    assert str(excinfo.value).startswith("Coluna 'código do inep' não encontrada no arquivo.")


def test_read_school_list_aliases_padrao_nao_incluem_unidade_escolar(wb_bytes):
    data = wb_bytes({"Escolas": [
        ["Código do Inep", "Unidade Escolar"],
        ["123", "Escola C"],
    ]})
    with pytest.raises(ValueError):
        read_school_list(io.BytesIO(data))


# ───────────── read_school_list — modo verificação ──────────────


def test_read_school_list_tolera_nome_ausente_quando_permitido(wb_bytes):
    data = wb_bytes({"Escolas": [["Código do Inep"], ["123"]]})
    assert read_school_list(io.BytesIO(data), require_nome=False) == [
        {"codigo_inep": "123", "nome_unidade": ""},
    ]


def test_read_school_list_alias_unidade_escolar(wb_bytes):
    data = wb_bytes({"Escolas": [
        ["Código do Inep", "Unidade Escolar"],
        ["123", "Escola C"],
    ]})
    aliases = ("nome da unidade", "nome da unidade escolar", "unidade escolar")
    assert read_school_list(io.BytesIO(data), require_nome=False, nome_aliases=aliases) == [
        {"codigo_inep": "123", "nome_unidade": "Escola C"},
    ]
