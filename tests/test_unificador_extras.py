"""Testes golden de lacunas de `unificador_inconsistencias.src.processor`.

O fluxo principal (`build_school_reports_zip` ponta a ponta) já é coberto por
`test_unificador_inconsistencias.py`; aqui ficam os helpers privados, os
caminhos de erro e os detalhes de escrita que ainda não tinham teste.

Observações pinadas:

- `_text`: float inteiro vira string de inteiro ("33000001.0" → "33000001");
  `None`/`NaN`/`pd.NA` viram "".
- `_normalize_inep`: aceita o sufixo `.0`/`.00` (vindo de planilhas) e exige
  `33` + 6 dígitos; a mensagem de erro inclui a localização.
- `read_active_schools`: usa as **duas primeiras** colunas, ignora linhas
  totalmente vazias e rejeita nome vazio sem descartar o restante do arquivo.
- `_read_report`: acumula os cabeçalhos de todas as abas por nome exato (por
  isso "Código INEP" e "Código do Inep" coexistem na lista de colunas),
  agrupa por código normalizado e **preserva os valores crus** nos registros.
  Aba vazia (sem cabeçalho) sozinha vira o erro "não contém linhas com
  cabeçalho e código INEP".
- `_write_report_sheet`: folha de mensagem usa só A1 com largura presa a
  [20, 60]; folha de dados congela A2, aplica filtro e limita larguras a
  [10, 50].
- `_safe_filename`: troca caracteres proibidos por "_", apara pontos finais,
  trunca em 180 e cai para "unidade_escolar" quando sobra vazio.
- Colisão de nomes de arquivo é detectada com `casefold` (caixa não salva).
"""

from __future__ import annotations

import io
import re
import zipfile

import openpyxl
import pandas as pd
import pytest

from apps.unificador_inconsistencias.src.processor import (
    _excel_value,
    _normalize_header,
    _normalize_inep,
    _read_report,
    _safe_filename,
    _text,
    _write_report_sheet,
    build_school_reports_zip,
    output_filename,
    read_active_schools,
)

# ─────────────────────────── _text ───────────────────────────

_TEXT = [
    pytest.param(None, "", id="none"),
    pytest.param(float("nan"), "", id="nan"),
    pytest.param(pd.NA, "", id="pd-na"),
    pytest.param(33000001.0, "33000001", id="float-inteiro"),
    pytest.param(1.5, "1.5", id="float-quebrado"),
    pytest.param(42, "42", id="int"),
    pytest.param("  x  ", "x", id="str-espacos"),
]


@pytest.mark.parametrize("valor,esperado", _TEXT)
def test_text(valor, esperado):
    assert _text(valor) == esperado


# ──────────────────────── _normalize_header ──────────────────

_NORMALIZE_HEADER = [
    pytest.param("Código do Inep", "codigodoinep", id="acentos-espacos"),
    pytest.param("CÓDIGO INEP.", "codigoinep", id="caixa-alta-pontuacao"),
    pytest.param("código-do INEP!", "codigodoinep", id="hifen-exclamacao"),
    pytest.param("Nome_da Unidade", "nomedaunidade", id="sublinhado"),
]


@pytest.mark.parametrize("valor,esperado", _NORMALIZE_HEADER)
def test_normalize_header(valor, esperado):
    assert _normalize_header(valor) == esperado


# ───────────────────────── _normalize_inep ───────────────────

_NORMALIZE_INEP = [
    pytest.param("33000001", "33000001", id="puro"),
    pytest.param("33000001.0", "33000001", id="sufixo-zero"),
    pytest.param("33000001.00", "33000001", id="sufixo-dois-zeros"),
    pytest.param(" 33000001 ", "33000001", id="espacos"),
    pytest.param(33000001.0, "33000001", id="float"),
]


@pytest.mark.parametrize("valor,esperado", _NORMALIZE_INEP)
def test_normalize_inep(valor, esperado):
    assert _normalize_inep(valor, "linha 2") == esperado


def test_normalize_inep_erro_traz_localizacao():
    with pytest.raises(ValueError) as excinfo:
        _normalize_inep("32000001", "linha 2 da relação")
    assert str(excinfo.value) == (
        "Código INEP inválido em linha 2 da relação: '32000001'. "
        "O código deve ter 8 dígitos e iniciar com 33."
    )


def test_normalize_inep_rejeita_sufixo_nao_zero():
    with pytest.raises(ValueError):
        _normalize_inep("33000001.5", "x")


# ─────────────────────── read_active_schools ─────────────────

def test_read_active_schools_normaliza_e_ignora_vazias(wb_bytes):
    data = wb_bytes({"Escolas": [
        ["Código INEP", "Nome", "Extra"],
        [" 33000001.0 ", " Escola Um ", "ignorar"],
        ["", "", ""],
        ["33000002", "Escola Dois", "ignorar"],
    ]})
    assert read_active_schools(data) == [
        {"codigo_inep": "33000001", "nome_unidade": "Escola Um"},
        {"codigo_inep": "33000002", "nome_unidade": "Escola Dois"},
    ]


def test_read_active_schools_exige_duas_colunas(wb_bytes):
    data = wb_bytes({"Escolas": [["Código"], ["33000001"]]})
    with pytest.raises(ValueError) as excinfo:
        read_active_schools(data)
    assert str(excinfo.value) == (
        "A relação de escolas ativas deve conter pelo menos duas colunas: "
        "código INEP na primeira e nome da unidade na segunda."
    )


def test_read_active_schools_arquivo_ilegivel():
    with pytest.raises(ValueError) as excinfo:
        read_active_schools(b"isto nao e xlsx")
    assert str(excinfo.value).startswith("Não foi possível ler a relação de escolas ativas: ")


def test_read_active_schools_nome_vazio(wb_bytes):
    data = wb_bytes({"Escolas": [["Código INEP", "Nome"], ["33000001", ""]]})
    with pytest.raises(ValueError) as excinfo:
        read_active_schools(data)
    assert str(excinfo.value) == "Nome da unidade vazio em linha 2 da relação de escolas ativas."


def test_read_active_schools_sem_unidades(wb_bytes):
    data = wb_bytes({"Escolas": [["Código INEP", "Nome"]]})
    with pytest.raises(ValueError, match="não contém unidades válidas"):
        read_active_schools(data)


# ─────────────────────────── _read_report ────────────────────

def test_read_report_mescla_abas_e_acumula_colunas(wb_bytes):
    report = wb_bytes({
        "Unidades": [
            ["Código do Inep", "Aba", "Detalhes"],
            ["33000001", "Identificação", "Campo obrigatório vazio"],
            ["", "", ""],
        ],
        "Endereços": [
            ["Código INEP", "Município"],
            ["33000001", "São Paulo"],
            ["33000002", "Campinas"],
        ],
    })
    columns, rows_by_code = _read_report(report, "Unidades")
    assert columns == ["Código do Inep", "Aba", "Detalhes", "Código INEP", "Município"]
    assert list(rows_by_code) == ["33000001", "33000002"]
    assert rows_by_code["33000001"] == [
        {
            "Código do Inep": "33000001",
            "Aba": "Identificação",
            "Detalhes": "Campo obrigatório vazio",
        },
        {"Código INEP": "33000001", "Município": "São Paulo"},
    ]
    assert rows_by_code["33000002"] == [
        {"Código INEP": "33000002", "Município": "Campinas"},
    ]


def test_read_report_chave_normalizada_e_valor_cru(wb_bytes):
    report = wb_bytes({"T": [
        ["Código do Inep", "Detalhes"],
        [" 33000001.0 ", "ok"],
    ]})
    _, rows_by_code = _read_report(report, "Unidades")
    assert rows_by_code == {
        "33000001": [{"Código do Inep": " 33000001.0 ", "Detalhes": "ok"}],
    }


def test_read_report_aba_sem_codigo_inep(wb_bytes):
    report = wb_bytes({"Relatório": [["Unidade Escolar", "Detalhes"], ["Escola Um", "Erro"]]})
    with pytest.raises(ValueError) as excinfo:
        _read_report(report, "Unidades")
    assert str(excinfo.value) == (
        "O relatório 'Unidades', aba 'Relatório', não possui uma coluna "
        "de código INEP (por exemplo, 'Código do Inep')."
    )


def test_read_report_so_com_aba_vazia(wb_bytes):
    report = wb_bytes({"Vazia": []})
    with pytest.raises(ValueError) as excinfo:
        _read_report(report, "Unidades")
    assert str(excinfo.value) == (
        "O relatório 'Unidades' não contém linhas com cabeçalho e código INEP."
    )


def test_read_report_codigo_invalido_traz_local(wb_bytes):
    report = wb_bytes({"T": [["Código do Inep"], ["33000001"], ["999"]]})
    with pytest.raises(ValueError) as excinfo:
        _read_report(report, "Unidades")
    assert str(excinfo.value) == (
        "Código INEP inválido em linha 3 da aba 'T' do relatório 'Unidades': '999'. "
        "O código deve ter 8 dígitos e iniciar com 33."
    )


def test_read_report_arquivo_ilegivel():
    with pytest.raises(ValueError) as excinfo:
        _read_report(b"x", "Unidades")
    assert str(excinfo.value).startswith("Não foi possível ler o relatório 'Unidades': ")


# ─────────────────────────── _excel_value ────────────────────

def test_excel_value():
    assert _excel_value(None) is None
    assert _excel_value(float("nan")) is None
    assert _excel_value("=1+1") == "'=1+1"
    assert _excel_value("texto") == "texto"
    convertido = _excel_value(pd.Series([7], dtype="int64").iloc[0])
    assert convertido == 7
    assert isinstance(convertido, int)  # escalar numpy vira int nativo


# ─────────────────────── _write_report_sheet ─────────────────

def _planilha_vazia() -> openpyxl.Workbook:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    return wb


def test_write_report_sheet_mensagem():
    wb = _planilha_vazia()
    _write_report_sheet(wb, "T", [], [], "Mensagem")
    ws = wb["T"]
    assert ws.cell(1, 1).value == "Mensagem"
    assert ws.column_dimensions["A"].width == 20
    assert ws.cell(2, 1).value is None


def test_write_report_sheet_mensagem_larga_tem_limite():
    wb = _planilha_vazia()
    _write_report_sheet(wb, "T", [], [], "x" * 100)
    assert wb["T"].column_dimensions["A"].width == 60


def test_write_report_sheet_dados():
    wb = _planilha_vazia()
    _write_report_sheet(wb, "T", ["A", "B"], [{"A": "x" * 60, "B": "yy"}], None)
    ws = wb["T"]
    assert [c.value for c in ws[1]] == ["A", "B"]
    assert ws.cell(2, 1).value == "x" * 60
    assert ws.cell(2, 2).value == "yy"
    assert ws.freeze_panes == "A2"
    assert ws.auto_filter.ref == "A1:B2"
    assert ws.column_dimensions["A"].width == 50
    assert ws.column_dimensions["B"].width == 10


# ──────────────── build_school_reports_zip (extras) ──────────

def test_categorias_de_relatorio_desconhecidas():
    with pytest.raises(ValueError, match="categorias de relatório desconhecidas"):
        build_school_reports_zip(b"", {"categoria-inexistente": b"x"}, set())
    with pytest.raises(ValueError, match="categorias de relatório desconhecidas"):
        build_school_reports_zip(b"", {}, {"categoria-inexistente"})


def test_relatorio_multia_aba_gera_colunas_acumuladas(wb_bytes):
    escolas = wb_bytes({"Escolas": [["Código INEP", "Nome"], ["33000001", "Escola Um"]]})
    relatorio = wb_bytes({
        "Identificação": [
            ["Código do Inep", "Detalhes"],
            ["33000001", "Campo vazio"],
        ],
        "Endereço": [
            ["Código do Inep", "Município"],
            ["33000001", "São Paulo"],
        ],
    })
    archive_bytes, stats = build_school_reports_zip(
        escolas,
        {"unidades": relatorio},
        {"gestores", "turmas", "alunos", "professores"},
    )
    assert stats["by_type"]["unidades"]["issues"] == 2
    assert stats["by_type"]["unidades"]["units"] == 1

    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        wb = openpyxl.load_workbook(io.BytesIO(archive.read(archive.namelist()[0])))
    assert archive.namelist() == ["Escola Um.xlsx"]
    ws = wb["Cadastro da Unidade"]
    assert [c.value for c in ws[1]] == ["Código do Inep", "Detalhes", "Município"]
    assert [c.value for c in ws[2]] == ["33000001", "Campo vazio", None]
    assert [c.value for c in ws[3]] == ["33000001", None, "São Paulo"]


def test_nomes_de_arquivo_colidem_sem_diferenca_de_caixa(wb_bytes):
    escolas = wb_bytes({"Escolas": [
        ["Código INEP", "Nome"],
        ["33000001", "Escola Um"],
        ["33000002", "ESCOLA UM"],
    ]})
    with pytest.raises(ValueError, match="nomes de unidades escolares repetidos"):
        build_school_reports_zip(
            escolas,
            {},
            {"unidades", "gestores", "turmas", "alunos", "professores"},
        )


# ─────────────────────────── _safe_filename ──────────────────

_SAFE_FILENAME = [
    pytest.param('Escola "A"', 'Escola _A_', id="aspas"),
    pytest.param("Escola/Um\\Dois", "Escola_Um_Dois", id="barras"),
    pytest.param("Escola...", "Escola", id="pontos-finais"),
    pytest.param("...", "unidade_escolar", id="so-pontos"),
    pytest.param("", "unidade_escolar", id="vazio"),
    pytest.param("Esc\tola", "Esc_ola", id="controle"),
    pytest.param("Escola Normal", "Escola Normal", id="espacos-preservados"),
    pytest.param("A" * 200, "A" * 180, id="truncamento"),
]


@pytest.mark.parametrize("nome,esperado", _SAFE_FILENAME)
def test_safe_filename(nome, esperado):
    assert _safe_filename(nome) == esperado


def test_output_filename():
    assert re.fullmatch(
        r"unificador_inconsistencias_\d{2}-\d{2}-\d{4}\.zip", output_filename()
    )
