"""Testes golden de `rules/aluno.py` — validação curricular (congela o atual).

Cada ramo nomeado de `validate_aluno` tem caso positivo e negativo: localização,
transporte, regras de período (`G1`..`MI`) e regras de etapa (creche, pré, EJA,
fundamental 9 anos). As mensagens esperadas são copiadas do módulo; se um ramo
deixar de casar a coluna/etapa, o negativo falha — canário de fidelidade.

Observações pinadas:

- Idade é calculada em **31/03** do ano letivo: nascimento em 31/03 conta a
  idade completa; em 01/04 ainda não (fronteira coberta).
- `MSG_IDADE` é **deduplicada** por linha (`dict.fromkeys`): dois ramos que
  disparam juntos aparecem uma única vez.
- Sem `ano_letivo` (`None`), a idade nunca é calculada e nenhum erro de idade
  é emitido.
- O transporte usa igualdade literal com `"Sim"` (`"SIM"` não entra).
"""

from __future__ import annotations

import pytest

from apps.verificacao_inconsistencias.src.rules.aluno import (
    COL_ETAPA_ENSINO,
    COL_IDENTIFICACAO,
    COL_LOCALIZACAO,
    COL_NASCIMENTO,
    COL_NOME,
    COL_NOME_TURMA,
    COL_PODER_PUBLICO,
    COL_TRANSPORTE,
    MSG_IDADE,
    validate_aluno,
)

CODIGO = "33012345"
NOME = "Escola Teste"

# Valores reais do export (comparados após `_norm_etapa`: caixa e travessões).
ETAPA_CRECHE = "Educação infantil - creche (0 a 3 anos)"
ETAPA_PRE_ESCOLA = "Educação infantil - pré-escola (4 e 5 anos)"
ETAPA_EF_9_1 = "Ensino fundamental de 9 anos - 1º Ano"
ETAPA_EJA_INICIAIS = "EJA - Ensino fundamental - anos iniciais (1º segmento)"
ETAPA_EJA_FINAIS_2 = "EJA - Ensino fundamental - anos finais (2º segmento)"

MSG_LOCALIZACAO = "Sem Zona Residencial informada"
MSG_TRANSPORTE = "Transporte Escolar não informado como Municipal"


def _molde() -> dict[str, list]:
    """DataFrame 100% válido — 1º ano, 6 anos completos em 31/03/2026."""
    return {
        "Código do Inep": [CODIGO],
        "Nome da Unidade": [NOME],
        COL_IDENTIFICACAO: ["ID001"],
        COL_NOME: ["Aluno Teste"],
        COL_NASCIMENTO: ["10/02/2020"],
        COL_NOME_TURMA: ["1AM01"],
        COL_ETAPA_ENSINO: [ETAPA_EF_9_1],
        COL_LOCALIZACAO: ["Urbana"],
        COL_TRANSPORTE: ["Não"],
        COL_PODER_PUBLICO: [""],
    }


def _validar(df, overrides: dict | None = None, ano: int | None = 2026) -> list[dict]:
    dados = _molde()
    dados.update({coluna: [valor] for coluna, valor in (overrides or {}).items()})
    return validate_aluno(df(dados), [], ano)


def test_linha_valida(df):
    assert _validar(df) == []


def test_sem_ano_letivo_nao_avalia_idade(df):
    overrides = {
        COL_NOME_TURMA: "G1M01",
        COL_ETAPA_ENSINO: ETAPA_CRECHE,
        COL_NASCIMENTO: "15/01/2000",
    }
    assert _validar(df, overrides, ano=None) == []
    assert [r["erros"] for r in _validar(df, overrides)] == [[MSG_IDADE]]


def test_msg_idade_deduplicada(df):
    # 7 anos em turma "P2" (esperado 5) e etapa pré-escola (esperado 4-5):
    # os dois ramos disparam juntos e a mensagem aparece uma única vez.
    resultados = _validar(df, {
        COL_NOME_TURMA: "P2M01",
        COL_ETAPA_ENSINO: ETAPA_PRE_ESCOLA,
        COL_NASCIMENTO: "15/01/2019",
    })
    assert [r["erros"] for r in resultados] == [[MSG_IDADE]]


def test_campos_de_saida(df):
    resultados = _validar(df, {COL_LOCALIZACAO: ""})
    assert resultados == [{
        "codigo_inep": CODIGO,
        "nome_unidade": NOME,
        "nome": "Aluno Teste",
        "identificacao_unica": "ID001",
        "data_nascimento": "10/02/2020",
        "nome_turma": "1AM01",
        "etapa_ensino": ETAPA_EF_9_1,
        "idade": 6,
        "periodo": "1A",
        "tipo_validacao": "aluno_curricular",
        "status": "inconsistente",
        "erros": [MSG_LOCALIZACAO],
        "detalhes": MSG_LOCALIZACAO,
    }]


def test_multiplos_erros_na_mesma_linha(df):
    resultados = _validar(df, {
        COL_LOCALIZACAO: "",
        COL_TRANSPORTE: "Sim",
        COL_PODER_PUBLICO: "Estadual",
        COL_NASCIMENTO: "01/04/2020",  # 5 anos em 31/03/2026
    })
    assert [r["erros"] for r in resultados] == [[MSG_LOCALIZACAO, MSG_TRANSPORTE, MSG_IDADE]]
    assert resultados[0]["detalhes"] == "; ".join([MSG_LOCALIZACAO, MSG_TRANSPORTE, MSG_IDADE])


_LOCALIZACAO = [
    pytest.param("", id="vazia"),
    pytest.param("--", id="traco-duplo"),
    pytest.param("-", id="traco"),
    pytest.param(None, id="none"),
]


@pytest.mark.parametrize("valor", _LOCALIZACAO)
def test_localizacao_vazia(df, valor):
    assert [r["erros"] for r in _validar(df, {COL_LOCALIZACAO: valor})] == [[MSG_LOCALIZACAO]]


_TRANSPORTE = [
    pytest.param("Sim", "Estadual", [MSG_TRANSPORTE], id="sim-nao-municipal"),
    pytest.param("Sim", "", [MSG_TRANSPORTE], id="sim-poder-vazio"),
    pytest.param("Sim", "Municipal", [], id="sim-municipal-ok"),
    pytest.param("Não", "", [], id="nao-sem-checagem"),
    pytest.param("SIM", "Estadual", [], id="sim-maiusculo-nao-entra"),
]


@pytest.mark.parametrize("transporte,poder,esperado", _TRANSPORTE)
def test_transporte(df, transporte, poder, esperado):
    resultados = _validar(df, {COL_TRANSPORTE: transporte, COL_PODER_PUBLICO: poder})
    assert [r["erros"] for r in resultados] == ([esperado] if esperado else [])


_IDADES = [
    # período (2 primeiros caracteres do nome da turma)
    pytest.param("G1M01", ETAPA_CRECHE, "01/06/2025", [], id="g1-0-ok"),
    pytest.param("G1M01", ETAPA_CRECHE, "15/01/2025", [], id="g1-1-ok"),
    pytest.param("G1M01", ETAPA_CRECHE, "15/01/2024", [MSG_IDADE], id="g1-2-fora"),
    pytest.param("G2M01", ETAPA_CRECHE, "15/01/2024", [], id="g2-2-ok"),
    pytest.param("G2M01", ETAPA_CRECHE, "15/01/2023", [MSG_IDADE], id="g2-3-fora"),
    pytest.param("G3M01", ETAPA_CRECHE, "15/01/2023", [], id="g3-3-ok"),
    pytest.param("G3M01", ETAPA_CRECHE, "15/01/2022", [MSG_IDADE], id="g3-4-fora"),
    pytest.param("P1M01", ETAPA_PRE_ESCOLA, "15/01/2022", [], id="p1-4-ok"),
    pytest.param("P1M01", ETAPA_PRE_ESCOLA, "15/01/2021", [MSG_IDADE], id="p1-5-fora"),
    pytest.param("P2M01", ETAPA_PRE_ESCOLA, "15/01/2021", [], id="p2-5-ok"),
    pytest.param("P2M01", ETAPA_PRE_ESCOLA, "15/01/2020", [MSG_IDADE], id="p2-6-fora"),
    pytest.param("MIM01", ETAPA_PRE_ESCOLA, "15/01/2021", [], id="mi-5-ok"),
    pytest.param("MIM01", ETAPA_PRE_ESCOLA, "15/01/2020", [MSG_IDADE], id="mi-6-fora"),
    # etapas (sem período com regra própria)
    pytest.param("1AM01", ETAPA_CRECHE, "15/01/2022", [MSG_IDADE], id="creche-4-fora"),
    pytest.param("1AM01", ETAPA_PRE_ESCOLA, "15/01/2023", [MSG_IDADE], id="pre-3-fora"),
    pytest.param("1AM01", ETAPA_EJA_INICIAIS, "15/01/2012", [MSG_IDADE], id="eja-inic-14-fora"),
    pytest.param("1AM01", ETAPA_EJA_INICIAIS, "15/01/2011", [], id="eja-inic-15-ok"),
    pytest.param("1AM01", ETAPA_EJA_FINAIS_2, "15/01/2012", [MSG_IDADE], id="eja-fin2-14-fora"),
    pytest.param("1AM01", ETAPA_EF_9_1, "15/01/2021", [MSG_IDADE], id="ef9-5-fora"),
    pytest.param("1AM01", ETAPA_EF_9_1, "15/01/2020", [], id="ef9-6-ok"),
    # fronteira do corte em 31/03
    pytest.param("1AM01", ETAPA_EF_9_1, "31/03/2020", [], id="fronteira-31-03-ok"),
    pytest.param("1AM01", ETAPA_EF_9_1, "01/04/2020", [MSG_IDADE], id="fronteira-01-04-fora"),
]


@pytest.mark.parametrize("turma,etapa,nascimento,esperado", _IDADES)
def test_idade(df, turma, etapa, nascimento, esperado):
    resultados = _validar(df, {
        COL_NOME_TURMA: turma,
        COL_ETAPA_ENSINO: etapa,
        COL_NASCIMENTO: nascimento,
    })
    assert [r["erros"] for r in resultados] == ([esperado] if esperado else [])
