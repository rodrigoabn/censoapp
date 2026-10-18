"""Testes golden de `rules/aluno.py` — listagens de apoio (congela o atual).

Cobre `find_matriculas_duplicadas`, `extrair_alunos_sem_cpf` e
`levantamento_cor_raca`, com os mesmos princípios dos demais goldens: valores
pinados a partir do código de produção e asserções exatas de saída.

Observações pinadas:

- CPF só conta quando tem **11 dígitos** após extração (`_cpf_digitos`);
  formatos mascarado ("123.456.789-09") e cru ("12345678909") são equivalentes.
- CPF/identificação vazios ou "--" (`_normalizar`) não entram nas contagens.
- Ordenação de `find_matriculas_duplicadas`: (identificação, cpf, inep,
  matrícula) comparados como texto; `extrair_alunos_sem_cpf`: (inep, nome).
- `levantamento_cor_raca` agrega por (código, nome da unidade) **na ordem de
  primeira aparição**; baldes por substring ("branca", "preta", "parda",
  "amarela", "indígena"/"indigena", "declar") e o resto em `sem_informacao`.
- O campo `cpf` das listagens preserva o valor original da célula.
"""

from __future__ import annotations

from apps.verificacao_inconsistencias.src.rules.aluno import (
    COL_COR_RACA,
    COL_CPF,
    COL_IDENTIFICACAO,
    COL_MATRICULA,
    COL_NOME,
    COL_NOME_TURMA,
    COL_TURMA,
    extrair_alunos_sem_cpf,
    find_matriculas_duplicadas,
    levantamento_cor_raca,
)

CODIGO = "33012345"
NOME = "Escola Teste"


def _aluno(
    cpf: str = "",
    idu: str = "",
    *,
    inep: str = CODIGO,
    nome_unidade: str = NOME,
    nome: str = "Aluno",
    matricula: str = "",
    turma: str = "",
    nome_turma: str = "",
) -> dict:
    return {
        "Código do Inep": inep,
        "Nome da Unidade": nome_unidade,
        COL_NOME: nome,
        COL_IDENTIFICACAO: idu,
        COL_CPF: cpf,
        COL_MATRICULA: matricula,
        COL_TURMA: turma,
        COL_NOME_TURMA: nome_turma,
    }


def _aluno_cor(valor, *, inep: str = CODIGO, nome_unidade: str = NOME) -> dict:
    linha = _aluno(inep=inep, nome_unidade=nome_unidade)
    linha[COL_COR_RACA] = valor
    return linha


def test_cpf_duplicado_aceita_mascara_equivalente(df):
    resultados = find_matriculas_duplicadas(df([
        _aluno(cpf="123.456.789-09", idu="A1", matricula="1"),
        _aluno(cpf="12345678909", idu="A2", matricula="2"),
    ]))
    assert len(resultados) == 2
    assert resultados[0] == {
        "codigo_inep": CODIGO,
        "nome_unidade": NOME,
        "nome": "Aluno",
        "identificacao_unica": "A1",
        "cpf": "123.456.789-09",
        "motivo": "CPF duplicado",
        "codigo_matricula": "1",
        "codigo_turma": "",
        "nome_turma": "",
    }
    assert [r["cpf"] for r in resultados] == ["123.456.789-09", "12345678909"]
    assert [r["motivo"] for r in resultados] == ["CPF duplicado", "CPF duplicado"]


def test_identificacao_unica_duplicada(df):
    resultados = find_matriculas_duplicadas(df([
        _aluno(cpf="11111111111", idu="IDX"),
        _aluno(cpf="22222222222", idu="IDX"),
    ]))
    assert [r["motivo"] for r in resultados] == [
        "Identificação única duplicada", "Identificação única duplicada",
    ]
    assert [r["cpf"] for r in resultados] == ["11111111111", "22222222222"]


def test_cpf_e_identificacao_duplicados_na_mesma_linha(df):
    resultados = find_matriculas_duplicadas(df([
        _aluno(cpf="11111111111", idu="ID1"),
        _aluno(cpf="11111111111", idu="ID1"),
    ]))
    assert [r["motivo"] for r in resultados] == [
        "CPF duplicado e Identificação única duplicada",
        "CPF duplicado e Identificação única duplicada",
    ]


def test_sem_duplicatas_retorna_vazio(df):
    resultados = find_matriculas_duplicadas(df([
        _aluno(cpf="11111111111", idu="A1"),
        _aluno(cpf="22222222222", idu="A2"),
    ]))
    assert resultados == []


def test_cpf_e_identificacao_vazios_nao_contam(df):
    resultados = find_matriculas_duplicadas(df([
        _aluno(cpf="", idu="--"),
        _aluno(cpf="--", idu=""),
    ]))
    assert resultados == []


def test_cpf_curto_nao_conta(df):
    resultados = find_matriculas_duplicadas(df([
        _aluno(cpf="123", idu="A1"),
        _aluno(cpf="123", idu="A2"),
    ]))
    assert resultados == []


def test_ordem_de_saida_por_inep_e_matricula(df):
    resultados = find_matriculas_duplicadas(df([
        _aluno(cpf="11111111111", idu="ID9", inep="99999999", matricula="5"),
        _aluno(cpf="11111111111", idu="ID9", inep="11111111", matricula="9"),
        _aluno(cpf="11111111111", idu="ID9", inep="11111111", matricula="3"),
    ]))
    assert [r["codigo_matricula"] for r in resultados] == ["3", "9", "5"]


def test_sem_cpf_inclui_traco_e_vazio(df):
    resultados = extrair_alunos_sem_cpf(df([
        _aluno(cpf="--", idu="A1", nome="Ana"),
        _aluno(cpf="", idu="A2", nome="Beto"),
        _aluno(cpf="111.111.111-11", idu="A3", nome="Carla"),
    ]))
    assert resultados == [{
        "codigo_inep": CODIGO,
        "nome_unidade": NOME,
        "identificacao_unica": "A1",
        "nome": "Ana",
        "cpf": "--",
    }, {
        "codigo_inep": CODIGO,
        "nome_unidade": NOME,
        "identificacao_unica": "A2",
        "nome": "Beto",
        "cpf": "",
    }]


def test_sem_cpf_ordena_por_inep_e_nome(df):
    resultados = extrair_alunos_sem_cpf(df([
        _aluno(cpf="--", idu="A1", nome="Zeca", inep="99999999"),
        _aluno(cpf="--", idu="A2", nome="Zeca", inep="11111111"),
        _aluno(cpf="--", idu="A3", nome="Ana", inep="11111111"),
    ]))
    assert [r["identificacao_unica"] for r in resultados] == ["A3", "A2", "A1"]


def test_cor_raca_buckets(df):
    valores = ["Branca", "Preta", "Parda", "Amarela", "Indígena", "Não declarada",
               "--", "Desconhecida", None]
    resultados = levantamento_cor_raca(df([_aluno_cor(valor) for valor in valores]))
    assert resultados == [{
        "codigo_inep": CODIGO,
        "nome_unidade": NOME,
        "preta": 1,
        "parda": 1,
        "branca": 1,
        "amarela": 1,
        "indigena": 1,
        "nao_declarado": 1,
        "sem_informacao": 3,
    }]


def test_cor_raca_caixa_e_acento(df):
    resultados = levantamento_cor_raca(df([
        _aluno_cor("INDIGENA"),
        _aluno_cor("indígena"),
        _aluno_cor("BRANCA"),
    ]))
    assert resultados == [{
        "codigo_inep": CODIGO,
        "nome_unidade": NOME,
        "preta": 0,
        "parda": 0,
        "branca": 1,
        "amarela": 0,
        "indigena": 2,
        "nao_declarado": 0,
        "sem_informacao": 0,
    }]


def test_cor_raca_agrega_por_unidade_e_preserva_ordem(df):
    resultados = levantamento_cor_raca(df([
        _aluno_cor("Branca", inep="11111111", nome_unidade="Escola A"),
        _aluno_cor(None, inep="11111111", nome_unidade="Escola A"),
        _aluno_cor("Preta", inep="22222222", nome_unidade="Escola B"),
    ]))
    assert resultados == [
        {
            "codigo_inep": "11111111",
            "nome_unidade": "Escola A",
            "preta": 0,
            "parda": 0,
            "branca": 1,
            "amarela": 0,
            "indigena": 0,
            "nao_declarado": 0,
            "sem_informacao": 1,
        },
        {
            "codigo_inep": "22222222",
            "nome_unidade": "Escola B",
            "preta": 1,
            "parda": 0,
            "branca": 0,
            "amarela": 0,
            "indigena": 0,
            "nao_declarado": 0,
            "sem_informacao": 0,
        },
    ]
