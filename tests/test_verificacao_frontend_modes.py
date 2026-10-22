"""Testes golden dos modos de relatório de `verificacao_inconsistencias.frontend`.

Pina a seleção de modo (`_modo_relatorio`) e a montagem da planilha de
inconsistências (`_build_xlsx`) para as cinco entradas do registro, além das
utilidades de escrita do módulo.

Observações pinadas:

- Precedência de `_modo_relatorio`: `split_tipo_turma` > `split_profissionais`
  > `split_aluno` > `"padrao"`.
- O número de colunas `INCONSISTENCIA N` é o **maior** número de erros de uma
  linha; linhas com menos erros são completadas com célula vazia.
- Cabeçalhos exatos por modo — destaque para os nomes técnicos em snake_case
  (`periodo_turma`, `verifica_integral`) no modo turma e para a ausência de
  coluna de período no modo aluno.
- Chaves ausentes em um resultado viram `""`; `erros` ausente ou `None` conta
  como lista vazia (não gera colunas).
- Os goldens refletem o arquivo **relido** (round-trip openpyxl): célula vazia
  (`""` ou ausente) volta como `None`.
- `_output_filename` usa a data corrente no formato dd-mm-aaaa.
"""

from __future__ import annotations

import io
import re

import openpyxl
import pytest

from apps.verificacao_inconsistencias.src import frontend

# ────────────────────────── _modo_relatorio ──────────────────

_MODOS = [
    pytest.param({}, "padrao", id="sem-flags"),
    pytest.param({"split_tipo_turma": True}, "turma", id="turma"),
    pytest.param({"split_profissionais": True}, "profissional", id="profissional"),
    pytest.param({"split_aluno": True}, "aluno", id="aluno"),
    pytest.param(
        {"split_tipo_turma": True, "split_profissionais": True, "split_aluno": True},
        "turma",
        id="turma-vence",
    ),
    pytest.param(
        {"split_profissionais": True, "split_aluno": True},
        "profissional",
        id="profissional-vence-aluno",
    ),
]


@pytest.mark.parametrize("config,esperado", _MODOS)
def test_modo_relatorio(config, esperado):
    assert frontend._modo_relatorio(config) == esperado


# ─────────────────────────── _build_xlsx ─────────────────────


def _grid(data: bytes) -> list[list]:
    ws = openpyxl.load_workbook(io.BytesIO(data)).active
    return [[c.value for c in row] for row in ws.iter_rows()]


def test_build_xlsx_padrao():
    data = frontend._build_xlsx([
        {
            "codigo_inep": "33000001",
            "nome_unidade": "Escola Um",
            "tipo_validacao": "unidades",
            "detalhes": "Detalhe",
        },
    ])
    assert _grid(data) == [
        ["Codigo do Inep", "Unidade Escolar", "Aba", "Detalhes"],
        ["33000001", "Escola Um", "unidades", "Detalhe"],
    ]


def test_build_xlsx_aluno():
    data = frontend._build_xlsx([
        {
            "codigo_inep": "33000001",
            "nome_unidade": "Escola Um",
            "identificacao_unica": "1100",
            "nome": "Ana",
            "data_nascimento": "15/01/2020",
            "idade": 6,
            "nome_turma": "1AM01",
            "etapa_ensino": "Ensino fundamental de 9 anos - 1º Ano",
            "erros": ["Idade incompatível com turma", "Sem Zona Residencial informada"],
        },
        {
            "codigo_inep": "33000002",
            "nome_unidade": "Escola Dois",
            "identificacao_unica": "1101",
            "nome": "Beto",
            "data_nascimento": "20/02/2019",
            "idade": 7,
            "nome_turma": "1BM02",
            "etapa_ensino": "Ensino fundamental de 9 anos - 2º Ano",
            "erros": [],
        },
    ], modo="aluno")
    assert _grid(data) == [
        [
            "Codigo do Inep", "Unidade Escolar", "Identificação Única", "Nome do Aluno",
            "Data de nascimento", "Idade", "Nome da Turma", "Etapa de ensino",
            "INCONSISTENCIA 1", "INCONSISTENCIA 2",
        ],
        [
            "33000001", "Escola Um", "1100", "Ana", "15/01/2020", 6, "1AM01",
            "Ensino fundamental de 9 anos - 1º Ano",
            "Idade incompatível com turma", "Sem Zona Residencial informada",
        ],
        [
            "33000002", "Escola Dois", "1101", "Beto", "20/02/2019", 7, "1BM02",
            "Ensino fundamental de 9 anos - 2º Ano", None, None,
        ],
    ]


def test_build_xlsx_turma():
    data = frontend._build_xlsx([
        {
            "codigo_inep": "33000001",
            "nome_unidade": "Escola Um",
            "nome_turma": "2BM02",
            "etapa_ensino": "Ensino Fundamental",
            "carga_horaria": "20:00",
            "periodo_turma": "2B",
            "verifica_integral": "M",
            "erros": ["Divergência entre Sigla e Etapa"],
        },
    ], modo="turma")
    assert _grid(data) == [
        [
            "Codigo do Inep", "Unidade Escolar", "Nome da Turma", "Etapa de ensino",
            "Carga horária semanal (hh:mm)", "periodo_turma", "verifica_integral",
            "INCONSISTENCIA 1",
        ],
        [
            "33000001", "Escola Um", "2BM02", "Ensino Fundamental", "20:00", "2B", "M",
            "Divergência entre Sigla e Etapa",
        ],
    ]


def test_build_xlsx_profissional_com_linha_vazia():
    data = frontend._build_xlsx([
        {
            "codigo_inep": "33000001",
            "nome_unidade": "Escola Um",
            "nome_profissional": "Prof Um",
            "identificacao_unica": "P001",
            "erros": ["Zona da residência não informada"],
        },
        {},
    ], modo="profissional")
    assert _grid(data) == [
        [
            "Codigo do Inep", "Unidade Escolar", "Nome do Profissional", "Identificação Única",
            "INCONSISTENCIA 1",
        ],
        ["33000001", "Escola Um", "Prof Um", "P001", "Zona da residência não informada"],
        [None, None, None, None, None],
    ]


def test_build_xlsx_erros_none_nao_gera_colunas():
    data = frontend._build_xlsx(
        [{"codigo_inep": "33000001", "erros": None}],
        modo="turma",
    )
    assert _grid(data) == [
        [
            "Codigo do Inep", "Unidade Escolar", "Nome da Turma", "Etapa de ensino",
            "Carga horária semanal (hh:mm)", "periodo_turma", "verifica_integral",
        ],
        ["33000001", None, None, None, None, None, None],
    ]


def test_build_xlsx_sem_resultados_so_cabecalho():
    assert _grid(frontend._build_xlsx([], modo="aluno")) == [[
        "Codigo do Inep", "Unidade Escolar", "Identificação Única", "Nome do Aluno",
        "Data de nascimento", "Idade", "Nome da Turma", "Etapa de ensino",
    ]]
    assert _grid(frontend._build_xlsx([])) == [[
        "Codigo do Inep", "Unidade Escolar", "Aba", "Detalhes",
    ]]


def test_build_xlsx_titulo_da_aba():
    wb = openpyxl.load_workbook(io.BytesIO(frontend._build_xlsx([], modo="padrao")))
    assert wb.active.title == "Inconsistencias"


# ─────────── quantitativo de matrículas (localização diferenciada) ──────────


def _registros_quantitativo():
    return [
        {
            "codigo_inep": "33000001",
            "nome_unidade": "Escola Um",
            "total": 4,
            "contagens": {"Sim": 2, "Não": 1, "Sem informação": 1},
        },
        {
            "codigo_inep": "33000002",
            "nome_unidade": "Escola Dois",
            "total": 2,
            "contagens": {"Sim": 1, "Não": 1, "Sem informação": 0},
        },
    ]


def test_quantitativo_matriculas_xlsx_cabecalho_e_linhas():
    wb = openpyxl.load_workbook(
        io.BytesIO(frontend._quantitativo_matriculas_xlsx(_registros_quantitativo()))
    )
    ws = wb.active
    assert ws.title == "Quantitativo_Matriculas"
    linhas = list(ws.iter_rows(values_only=True))
    assert linhas[0] == (
        "Código do Inep", "Nome da Unidade",
        "Sim", "Não", "Sem informação", "Total de matrículas",
    )
    assert linhas[1] == ("33000001", "Escola Um", 2, 1, 1, 4)
    assert linhas[2] == ("33000002", "Escola Dois", 1, 1, 0, 2)


def test_quantitativo_matriculas_xlsx_sem_registros_so_cabecalho():
    wb = openpyxl.load_workbook(
        io.BytesIO(frontend._quantitativo_matriculas_xlsx([]))
    )
    ws = wb.active
    linhas = list(ws.iter_rows(values_only=True))
    assert len(linhas) == 1
    assert linhas[0][-1] == "Total de matrículas"


def test_quantitativo_matriculas_xlsx_colunas_pelo_primeiro_registro():
    """Os parâmetros viram colunas na ordem em que aparecem no registro."""
    registros = [{
        "codigo_inep": "1",
        "nome_unidade": "Escola",
        "total": 1,
        "contagens": {"Não": 1, "Sim": 1},
    }]
    wb = openpyxl.load_workbook(
        io.BytesIO(frontend._quantitativo_matriculas_xlsx(registros))
    )
    linhas = list(wb.active.iter_rows(values_only=True))
    assert linhas[0] == (
        "Código do Inep", "Nome da Unidade", "Não", "Sim", "Total de matrículas",
    )


# ────────────────────────── utilidades ───────────────────────


def test_texto_seguro():
    assert frontend._texto_seguro("=1+1") == "'=1+1"
    assert frontend._texto_seguro("ok") == "ok"
    assert frontend._texto_seguro(None) is None
    assert frontend._texto_seguro(5) == 5


def test_ajustar_larguras():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["a", "x" * 60])
    ws.append(["bb", "y"])
    frontend._ajustar_larguras(ws)
    assert ws.column_dimensions["A"].width == 10  # curto cai no mínimo
    assert ws.column_dimensions["B"].width == 50  # longo satura no máximo


def test_output_filename():
    nome = frontend._output_filename({"key": "turmas"})
    assert re.fullmatch(r"inconsistencias_turmas_\d{2}-\d{2}-\d{4}\.xlsx", nome)
    custom = frontend._output_filename({"key": "aluno"}, suffix="matriculas", ext="csv")
    assert re.fullmatch(r"matriculas_aluno_\d{2}-\d{2}-\d{4}\.csv", custom)
