"""Testes golden de `rules/turmas.py` — parte curricular (congela o atual).

Cada regra nomeada de `_validar_linha` tem caso positivo (molde válido) e
negativo (célula sobrescrita). As mensagens esperadas são copiadas do módulo;
se uma regra deixar de encontrar a coluna, o negativo falha — canário.

Observações pinadas:

- O nome da turma usa o valor **cru** para detectar espaços (um nome com
  espaço interno é erro; a checagem de tamanho usa o valor stripado).
- `df_aee`/`df_atv` dos parâmetros de `validate_turmas` não são usados pela
  função (comportamento atual).
- `validate_turmas` concatena: curricular primeiro, escolarização depois.
"""

from __future__ import annotations

import pandas as pd
import pytest

from apps.verificacao_inconsistencias.src.rules.turmas import (
    _AREA_MULTIETAPA_EF_1_5,
    _COLS_ESPECIAIS,
    ETAPA_EF_9,
    ETAPA_EJA_ANOS_INICIAIS,
    MSG_SIGLA_ETAPA,
    ORGANIZACAO_EJA,
    ORGANIZACAO_SEMESTRAL,
    TIPO_CURRICULAR,
    validate_turmas,
)

CODIGO = "33012345"
NOME = "Escola Teste"

MSG_TIPO = "Tipo de turma deve ser 'Curricular (etapa de ensino)'."
MSG_NOME_VAZIO = "Nome da turma não informado."
MSG_NOME_TAMANHO = "Nome da turma deve ter exatamente 5 caracteres."
MSG_NOME_ESPACO = "Nome da turma não pode conter espaços."
MSG_CHAR3 = "O 3º caractere do nome da turma deve ser 'M', 'T', 'N' ou 'I'."
MSG_EJA_FORMAS = (
    "Quando 'Etapa Agregada' for EJA, 'Formas de organização da turma' deve ser "
    "'Períodos semestrais'."
)
MSG_EJA_MENOS_15 = "Carga horária semanal não pode ser menor que 15:00:00."
MSG_EJA_MAIS_20 = "Carga horária semanal não pode ser maior que 20:00:00."
MSG_EF_MENOS_20 = (
    "Para 'Etapa Agregada' de Ensino Fundamental ou Educação Infantil, a carga horária "
    "semanal não pode ser menor que 20:00:00."
)
MSG_I_MENOS_35 = (
    "Para turmas com 3º caractere 'I' no nome, a carga horária semanal deve ser "
    "maior ou igual a 35:00:00."
)
MSG_DIAS = (
    "'Dias da semana e horário de funcionamento' não pode conter 'Sábado' ou 'Domingo'."
)

AREA_ARTE = "Arte (Educação Artística, Teatro, Dança, Música, Artes Plásticas e outras)"
AREA_INGLES = "Língua /Literatura estrangeira - Inglês"


def _areas(*, sem: frozenset = frozenset(), extras: frozenset = frozenset()) -> str:
    return "|".join(sorted((_AREA_MULTIETAPA_EF_1_5 | set(extras)) - set(sem)))


def _molde() -> dict[str, list]:
    """DataFrame 100% válido — uma linha curricular."""
    return {
        "Código do Inep": [CODIGO],
        "Nome da Unidade": [NOME],
        "Nome da turma": ["1AM01"],
        "Tipo de turma": [TIPO_CURRICULAR],
        "Etapa Agregada": ["Ensino Fundamental"],
        "Formas de organização da turma": ["Anual"],
        "Etapa de ensino": [ETAPA_EF_9[0]],
        "Carga horária semanal (hh:mm)": ["25:00"],
        "Dias da semana e horário de funcionamento": ["Segunda-feira a sexta-feira"],
        "Áreas do conhecimento/componentes curriculares": [_areas()],
        _COLS_ESPECIAIS[0]: ["Não"],
        _COLS_ESPECIAIS[1]: ["Não"],
        _COLS_ESPECIAIS[2]: ["Não"],
    }


def _caso(overrides: dict | None = None) -> dict[str, list]:
    dados = _molde()
    dados.update({coluna: [valor] for coluna, valor in (overrides or {}).items()})
    return dados


def _validar(df, overrides: dict | None = None) -> list[dict]:
    return validate_turmas(pd.DataFrame(), pd.DataFrame(), df(_caso(overrides)))


def test_linha_valida(df):
    assert _validar(df) == []


def test_campos_de_saida(df):
    dados = _caso({"Tipo de turma": "AEE"})
    resultados = validate_turmas(pd.DataFrame(), pd.DataFrame(), df(dados))
    assert resultados == [{
        "codigo_inep": CODIGO,
        "nome_unidade": NOME,
        "nome_turma": "1AM01",
        "etapa_ensino": ETAPA_EF_9[0],
        "carga_horaria": "25:00",
        "periodo_turma": "1A",
        "verifica_integral": "M",
        "tipo_validacao": "turmas_curricular",
        "status": "inconsistente",
        "erros": [MSG_TIPO],
        "detalhes": MSG_TIPO,
    }]


def test_multiplos_erros_na_mesma_linha(df):
    resultados = _validar(df, {
        "Tipo de turma": "AEE",
        "Carga horária semanal (hh:mm)": "19:00",
        "Dias da semana e horário de funcionamento": "Sábado",
    })
    assert len(resultados) == 1
    assert resultados[0]["erros"] == [MSG_TIPO, MSG_EF_MENOS_20, MSG_DIAS]
    assert resultados[0]["detalhes"] == "; ".join([MSG_TIPO, MSG_EF_MENOS_20, MSG_DIAS])


def test_validate_turmas_ordem_curricular_depois_escolarizacao(df):
    df_escol = df({
        "Código do Inep": ["99123456"],
        "Nome da Unidade": ["Outra Escola"],
        "Nome da turma": ["2AM01"],
        "Etapa Agregada": ["Ensino Fundamental"],
        "Etapa de ensino": [ETAPA_EF_9[2]],
        "Carga horária semanal (hh:mm)": ["25:00"],
    })
    resultados = validate_turmas(
        pd.DataFrame(), pd.DataFrame(), df(_caso({"Tipo de turma": "AEE"})), df_escol
    )
    assert [r["tipo_validacao"] for r in resultados] == [
        "turmas_curricular", "turmas_escolarizacao",
    ]
    assert resultados[0]["erros"] == [MSG_TIPO]
    assert resultados[1]["erros"] == [MSG_SIGLA_ETAPA]


def test_validate_turmas_sem_escolarizacao(df):
    resultados = validate_turmas(
        pd.DataFrame(), pd.DataFrame(), df(_caso({"Tipo de turma": "AEE"}))
    )
    assert len(resultados) == 1
    assert resultados[0]["tipo_validacao"] == "turmas_curricular"


_NEGATIVOS = [
    pytest.param({"Tipo de turma": "AEE"}, [MSG_TIPO], id="tipo-turma"),
    pytest.param({"Nome da turma": ""}, [MSG_NOME_VAZIO], id="nome-vazio"),
    pytest.param({"Nome da turma": "1AM0"}, [MSG_NOME_TAMANHO], id="nome-curto"),
    pytest.param({"Nome da turma": "1AM001"}, [MSG_NOME_TAMANHO], id="nome-longo"),
    pytest.param({"Nome da turma": "1AM 1"}, [MSG_NOME_ESPACO], id="nome-com-espaco"),
    pytest.param({"Nome da turma": "1AX01"}, [MSG_CHAR3], id="char3-invalido"),
    pytest.param({"Etapa Agregada": ORGANIZACAO_EJA}, [MSG_EJA_FORMAS], id="eja-sem-semestral"),
    pytest.param(
        {"Etapa Agregada": ORGANIZACAO_EJA, "Formas de organização da turma": ORGANIZACAO_SEMESTRAL,
         "Etapa de ensino": ETAPA_EJA_ANOS_INICIAIS, "Carga horária semanal (hh:mm)": "14:00"},
        [MSG_EJA_MENOS_15], id="eja-menos-15h"),
    pytest.param(
        {"Etapa Agregada": ORGANIZACAO_EJA, "Formas de organização da turma": ORGANIZACAO_SEMESTRAL,
         "Etapa de ensino": ETAPA_EJA_ANOS_INICIAIS, "Carga horária semanal (hh:mm)": "21:00"},
        [MSG_EJA_MAIS_20], id="eja-mais-20h"),
    pytest.param(
        {"Carga horária semanal (hh:mm)": "19:00"}, [MSG_EF_MENOS_20], id="ef-menos-20h"),
    pytest.param(
        {"Nome da turma": "1AI01", "Carga horária semanal (hh:mm)": "30:00"},
        [MSG_I_MENOS_35], id="integral-menos-35h"),
    pytest.param(
        {"Dias da semana e horário de funcionamento": "Sábado"}, [MSG_DIAS], id="sabado"),
    pytest.param(
        {"Dias da semana e horário de funcionamento": "Domingo"}, [MSG_DIAS], id="domingo"),
    pytest.param(
        {"Áreas do conhecimento/componentes curriculares": _areas(sem=frozenset({AREA_ARTE}))},
        [f"'{AREA_ARTE}' não informado."], id="area-faltando"),
    pytest.param(
        {"Áreas do conhecimento/componentes curriculares": _areas(extras=frozenset({AREA_INGLES}))},
        [f"'{AREA_INGLES}' não deve ser informado."], id="area-extra"),
    pytest.param({_COLS_ESPECIAIS[0]: "Sim"}, [f"'{_COLS_ESPECIAIS[0]}' deve ser 'Não'."],
                 id="especial-1"),
    pytest.param({_COLS_ESPECIAIS[1]: "Sim"}, [f"'{_COLS_ESPECIAIS[1]}' deve ser 'Não'."],
                 id="especial-2"),
    pytest.param({_COLS_ESPECIAIS[2]: "Sim"}, [f"'{_COLS_ESPECIAIS[2]}' deve ser 'Não'."],
                 id="especial-3"),
]

_VALIDOS = [
    pytest.param({}, id="molde"),
    pytest.param({"Carga horária semanal (hh:mm)": "20:00"}, id="ef-fronteira-20h"),
    pytest.param({"Nome da turma": "1AI01", "Carga horária semanal (hh:mm)": "35:00"},
                 id="integral-fronteira-35h"),
    pytest.param(
        {"Etapa Agregada": ORGANIZACAO_EJA, "Formas de organização da turma": ORGANIZACAO_SEMESTRAL,
         "Etapa de ensino": ETAPA_EJA_ANOS_INICIAIS, "Carga horária semanal (hh:mm)": "15:00"},
        id="eja-fronteira-15h"),
    pytest.param(
        {"Etapa Agregada": ORGANIZACAO_EJA, "Formas de organização da turma": ORGANIZACAO_SEMESTRAL,
         "Etapa de ensino": ETAPA_EJA_ANOS_INICIAIS, "Carga horária semanal (hh:mm)": "20:00"},
        id="eja-fronteira-20h"),
]


@pytest.mark.parametrize("overrides,esperado", _NEGATIVOS)
def test_regra_negativa(df, overrides, esperado):
    resultados = _validar(df, overrides)
    assert len(resultados) == 1, resultados
    assert resultados[0]["erros"] == esperado


@pytest.mark.parametrize("overrides", _VALIDOS)
def test_linha_valida_variacoes(df, overrides):
    assert _validar(df, overrides) == []
