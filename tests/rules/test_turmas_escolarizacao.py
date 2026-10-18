"""Testes golden de `rules/turmas.py` — parte escolarização (congela o atual).

Cada ramo nomeado de `_validar_escolarizacao` tem caso positivo e negativo:
sigla↔etapa (`PERIODO_ETAPA_ESPERADA`), multietapa→`IF`, multi→`MA`,
correção→`NI`/`NF`, `MI` exige "Educação Infantil" na Etapa Agregada, cargas
`M`/`T` em [20h, 35h] e `I` ≥ 35h. As mensagens esperadas são copiadas do
módulo; se um ramo deixar de casar a etapa, o negativo falha — canário.

Observações pinadas:

- A mensagem `MSG_SIGLA_ETAPA` é **deduplicada por linha** (`dict.fromkeys`):
  disparos por dois ramos aparecem uma única vez.
- Carga `"--"` (placeholder do export) ⇒ `None` ⇒ sem checagem de carga.
"""

from __future__ import annotations

import pytest

from apps.verificacao_inconsistencias.src.rules.turmas import (
    ETAPA_AGREGADA_EDUCACAO_INFANTIL,
    ETAPA_CORRECAO_FLUXO,
    ETAPA_CRECHE,
    ETAPA_EF_9,
    ETAPA_EJA_ANOS_FINAIS_2,
    ETAPA_EJA_ANOS_INICIAIS,
    ETAPA_MULTI,
    ETAPA_MULTIETAPA,
    ETAPA_PRE_ESCOLA,
    MSG_CARGA_I,
    MSG_CARGA_M_T,
    MSG_SIGLA_ETAPA,
    validate_turmas_escolarizacao,
)

CODIGO = "33012345"
NOME = "Escola Teste"


def _molde() -> dict[str, list]:
    """DataFrame 100% válido — uma linha de escolarização ("1A" ↔ EF 1º ano)."""
    return {
        "Código do Inep": [CODIGO],
        "Nome da Unidade": [NOME],
        "Nome da turma": ["1AM01"],
        "Etapa Agregada": ["Ensino Fundamental"],
        "Etapa de ensino": [ETAPA_EF_9[0]],
        "Carga horária semanal (hh:mm)": ["25:00"],
    }


def _caso(overrides: dict | None = None) -> dict[str, list]:
    dados = _molde()
    dados.update({coluna: [valor] for coluna, valor in (overrides or {}).items()})
    return dados


def _erros(df, overrides: dict | None = None) -> list[str]:
    resultados = validate_turmas_escolarizacao(df(_caso(overrides)))
    assert len(resultados) <= 1, resultados
    return resultados[0]["erros"] if resultados else []


def test_linha_valida(df):
    assert validate_turmas_escolarizacao(df(_caso())) == []


def test_campos_de_saida(df):
    resultados = validate_turmas_escolarizacao(
        df(_caso({"Nome da turma": "2AM01", "Etapa de ensino": ETAPA_EF_9[2]}))
    )
    assert resultados == [{
        "codigo_inep": CODIGO,
        "nome_unidade": NOME,
        "nome_turma": "2AM01",
        "etapa_ensino": ETAPA_EF_9[2],
        "carga_horaria": "25:00",
        "periodo_turma": "2A",
        "verifica_integral": "M",
        "tipo_validacao": "turmas_escolarizacao",
        "status": "inconsistente",
        "erros": [MSG_SIGLA_ETAPA],
        "detalhes": MSG_SIGLA_ETAPA,
    }]


def test_multietapa_sem_if_deduplica_msg(df):
    # "1A" + etapa multietapa dispara a checagem sigla↔etapa E a exigência de
    # "IF": a mensagem aparece uma única vez.
    erros = _erros(df, {"Nome da turma": "1AM01", "Etapa de ensino": ETAPA_MULTIETAPA})
    assert erros == [MSG_SIGLA_ETAPA]


def test_mi_com_educacao_infantil_valida(df):
    assert _erros(df, {
        "Nome da turma": "MIM01",
        "Etapa Agregada": ETAPA_AGREGADA_EDUCACAO_INFANTIL,
    }) == []


def test_mi_sem_educacao_infantil(df):
    assert _erros(df, {"Nome da turma": "MIM01"}) == [MSG_SIGLA_ETAPA]


_SIGLAS = [
    pytest.param("1AM01", ETAPA_EF_9[0], False, id="1A-ok"),
    pytest.param("2AM01", ETAPA_EF_9[1], False, id="2A-ok"),
    pytest.param("2AM01", ETAPA_EF_9[2], True, id="2A-divergente"),
    pytest.param("1FM01", ETAPA_EJA_ANOS_INICIAIS, False, id="1F-eja-iniciais-ok"),
    pytest.param("5FM01", ETAPA_EJA_ANOS_INICIAIS, False, id="5F-eja-iniciais-ok"),
    pytest.param("6FM01", ETAPA_EJA_ANOS_FINAIS_2, False, id="6F-eja-finais2-ok"),
    pytest.param("9FM01", ETAPA_EJA_ANOS_FINAIS_2, False, id="9F-eja-finais2-ok"),
    pytest.param("1FM01", ETAPA_EJA_ANOS_FINAIS_2, True, id="1F-finais2-divergente"),
    pytest.param("6FM01", ETAPA_EJA_ANOS_INICIAIS, True, id="6F-iniciais-divergente"),
    pytest.param("G1M01", ETAPA_CRECHE, False, id="G1-creche-ok"),
    pytest.param("G2M01", ETAPA_PRE_ESCOLA, True, id="G2-pre-divergente"),
    pytest.param("P1M01", ETAPA_PRE_ESCOLA, False, id="P1-pre-ok"),
    pytest.param("P2M01", ETAPA_CRECHE, True, id="P2-creche-divergente"),
    pytest.param("MFM01", ETAPA_EJA_ANOS_INICIAIS, False, id="MF-iniciais-ok"),
    pytest.param("MFM01", ETAPA_EJA_ANOS_FINAIS_2, False, id="MF-finais2-ok"),
    pytest.param("MFM01", ETAPA_CRECHE, True, id="MF-creche-divergente"),
    pytest.param("NIM01", ETAPA_CORRECAO_FLUXO, False, id="NI-correcao-ok"),
    pytest.param("NFM01", ETAPA_CORRECAO_FLUXO, False, id="NF-correcao-ok"),
    pytest.param("NIM01", ETAPA_EF_9[0], True, id="NI-ef-divergente"),
    pytest.param("MAM01", ETAPA_MULTI, False, id="MA-multi-ok"),
    pytest.param("MAM01", ETAPA_EF_9[0], True, id="MA-ef-divergente"),
    pytest.param("IFM01", ETAPA_MULTIETAPA, False, id="IF-multietapa-ok"),
]


@pytest.mark.parametrize("nome,etapa,divergente", _SIGLAS)
def test_sigla_etapa(df, nome, etapa, divergente):
    erros = _erros(df, {"Nome da turma": nome, "Etapa de ensino": etapa})
    assert erros == ([MSG_SIGLA_ETAPA] if divergente else [])


_CARGAS = [
    pytest.param("1AM01", "19:00", [MSG_CARGA_M_T], id="M-abaixo-de-20"),
    pytest.param("1AT01", "36:00", [MSG_CARGA_M_T], id="T-acima-de-35"),
    pytest.param("1AM01", "20:00", [], id="M-fronteira-20"),
    pytest.param("1AT01", "35:00", [], id="T-fronteira-35"),
    pytest.param("1AI01", "34:00", [MSG_CARGA_I], id="I-abaixo-de-35"),
    pytest.param("1AI01", "35:00", [], id="I-fronteira-35"),
    pytest.param("1AM01", "--", [], id="carga-placeholder"),
]


@pytest.mark.parametrize("nome,carga,esperado", _CARGAS)
def test_carga_horaria(df, nome, carga, esperado):
    assert _erros(df, {"Nome da turma": nome, "Carga horária semanal (hh:mm)": carga}) == esperado
