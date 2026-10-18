"""Testes golden de `rules/profissionais.py` — congelam o comportamento atual.

Cada regra nomeada de `_validar_linha` tem caso positivo (molde válido) e
negativo (célula sobrescrita). As mensagens esperadas são copiadas do módulo;
se uma regra deixar de casar a coluna, o negativo falha — canário de fidelidade.

Observações pinadas:

- `Área(s) do Itinerário formativo que leciona (IFA)` e `Tipo do curso ...`
  precisam ser literalmente `"-"`; qualquer outro valor (inclusive vazio)
  dispara \"Itinerário formativo não deve ser informado\".
- **Falso positivo conhecido (congelado, correção candidata à Fase 6)**: quando
  a coluna IFA/tipo do curso está *ausente*, `row.get(...)` vira `""`, que é
  diferente de `"-"` — a linha dispara o erro. Como os dois ids de regra são
  distintos, a mensagem aparece **duplicada** na lista `erros` da linha.
- `Situação Funcional` e `Cor/Raça` comparam por igualdade exata
  (caixa importa: `"contrato clt"`/`"não declarada"` não são capturados).
- Zonas usam apenas `strip` (um `"--"` conta como preenchido).
- Agrupamento por (código INEP, identificação única) com fallback para
  (código INEP, nome); erros são deduplicados por **id de regra** dentro do
  grupo, e os grupos saem na ordem de primeira aparição.
- `6º`..`9º` ano: professor (função ≠ apoio) sem \"Educação superior\" (exato)
  dispara \"Professor de Anos Finais Sem Ensino Superior\"; a etapa é comparada
  por substring sem diferenciar caixa.
"""

from __future__ import annotations

import pytest

from apps.verificacao_inconsistencias.src.rules.profissionais import (
    COL_COR,
    COL_ESCOLARIDADE,
    COL_ETAPA,
    COL_FUNCAO,
    COL_IDENTIFICACAO,
    COL_IFA,
    COL_LOCALIZACAO,
    COL_LOCALIZACAO_DIF,
    COL_SITUACAO,
    COL_TIPO_CURSO,
    ETAPAS_EF_6_9,
    FUNCAO_APOIO,
    validate_profissionais,
)

CODIGO = "33012345"
NOME = "Escola Teste"

MSG_SITUACAO = "Situação Funcional informada como 'Contrato CLT ou Terceirizado informado'"
MSG_ITINERARIO = "Itinerário formativo não deve ser informado"
MSG_COR = "Etnia informada como Não Declarado"
MSG_LOCALIZACAO = "Zona da residência não informada"
MSG_LOCALIZACAO_DIF = "Localização diferenciada não informada"
MSG_FUNDAMENTAL = "Escolarização do Profissional informada como Ensino fundamental"
MSG_SUPERIOR = "Professor de Anos Finais Sem Ensino Superior"


def _prof(overrides: dict | None = None) -> dict:
    """Uma linha 100% válida de profissional (professor do 1º ano)."""
    linha = {
        "Código do Inep": CODIGO,
        "Nome da Unidade": NOME,
        "Nome": "Professor Teste",
        COL_IDENTIFICACAO: "P001",
        COL_SITUACAO: "Concursado/efetivo/estável",
        COL_IFA: "-",
        COL_TIPO_CURSO: "-",
        COL_COR: "Parda",
        COL_LOCALIZACAO: "Urbana",
        COL_LOCALIZACAO_DIF: "Não se aplica",
        COL_ESCOLARIDADE: "Educação superior",
        COL_ETAPA: "Ensino fundamental de 9 anos - 1º Ano",
        COL_FUNCAO: "Professor(a)",
    }
    linha.update(overrides or {})
    return linha


def _validar(df, overrides: dict | None = None) -> list[dict]:
    return validate_profissionais(df([_prof(overrides)]), [])


def test_linha_valida(df):
    assert _validar(df) == []


def test_campos_de_saida(df):
    resultados = _validar(df, {COL_LOCALIZACAO: ""})
    assert resultados == [{
        "codigo_inep": CODIGO,
        "nome_unidade": NOME,
        "nome_profissional": "Professor Teste",
        "identificacao_unica": "P001",
        "tipo_validacao": "profissionais",
        "status": "inconsistente",
        "erros": [MSG_LOCALIZACAO],
        "detalhes": MSG_LOCALIZACAO,
    }]


def test_multiplos_erros_na_mesma_linha(df):
    resultados = _validar(df, {
        COL_SITUACAO: "Contrato CLT",
        COL_IFA: "Matemática",
        COL_COR: "Não declarada",
        COL_LOCALIZACAO: "",
    })
    assert len(resultados) == 1
    assert resultados[0]["erros"] == [MSG_SITUACAO, MSG_ITINERARIO, MSG_COR, MSG_LOCALIZACAO]
    assert resultados[0]["detalhes"] == "; ".join(
        [MSG_SITUACAO, MSG_ITINERARIO, MSG_COR, MSG_LOCALIZACAO]
    )


def test_ifa_e_tipo_curso_ausentes_disparam_falso_positivo(df):
    # Colunas ausentes viram "" ≠ "-": dois ids de regra, mensagem repetida.
    linha = _prof()
    del linha[COL_IFA]
    del linha[COL_TIPO_CURSO]
    resultados = validate_profissionais(df([linha]), [])
    assert resultados == [{
        "codigo_inep": CODIGO,
        "nome_unidade": NOME,
        "nome_profissional": "Professor Teste",
        "identificacao_unica": "P001",
        "tipo_validacao": "profissionais",
        "status": "inconsistente",
        "erros": [MSG_ITINERARIO, MSG_ITINERARIO],
        "detalhes": f"{MSG_ITINERARIO}; {MSG_ITINERARIO}",
    }]


def test_erros_deduplicados_no_mesmo_profissional(df):
    resultados = validate_profissionais(df([
        _prof({COL_LOCALIZACAO: ""}),
        _prof({COL_LOCALIZACAO: ""}),
    ]), [])
    assert len(resultados) == 1
    assert resultados[0]["erros"] == [MSG_LOCALIZACAO]


def test_profissionais_diferentes_geram_resultados_separados(df):
    resultados = validate_profissionais(df([
        _prof({COL_IDENTIFICACAO: "P001", COL_LOCALIZACAO: ""}),
        _prof({COL_IDENTIFICACAO: "P002", COL_COR: "Não declarada"}),
    ]), [])
    assert [r["identificacao_unica"] for r in resultados] == ["P001", "P002"]
    assert [r["erros"] for r in resultados] == [[MSG_LOCALIZACAO], [MSG_COR]]


def test_chave_usa_nome_quando_sem_identificacao(df):
    resultados = validate_profissionais(df([
        _prof({COL_IDENTIFICACAO: "", "Nome": "Maria", COL_LOCALIZACAO: ""}),
        _prof({COL_IDENTIFICACAO: "", "Nome": "Maria", COL_COR: "Não declarada"}),
        _prof({COL_IDENTIFICACAO: "", "Nome": "João", COL_LOCALIZACAO: ""}),
    ]), [])
    assert len(resultados) == 2
    assert resultados[0]["nome_profissional"] == "Maria"
    assert resultados[0]["erros"] == [MSG_LOCALIZACAO, MSG_COR]
    assert resultados[1]["nome_profissional"] == "João"
    assert resultados[1]["erros"] == [MSG_LOCALIZACAO]


def test_escolaridade_fundamental(df):
    resultados = _validar(df, {COL_ESCOLARIDADE: "Ensino fundamental"})
    assert [r["erros"] for r in resultados] == [[MSG_FUNDAMENTAL]]


def test_apoio_ignora_escolaridade_fundamental(df):
    assert _validar(df, {
        COL_FUNCAO: FUNCAO_APOIO,
        COL_ESCOLARIDADE: "Ensino fundamental",
    }) == []


def test_apoio_ignora_anos_finais(df):
    assert _validar(df, {
        COL_FUNCAO: FUNCAO_APOIO,
        COL_ETAPA: ETAPAS_EF_6_9[0],
        COL_ESCOLARIDADE: "Ensino médio",
    }) == []


_SITUACAO = [
    pytest.param({COL_SITUACAO: "Contrato CLT"}, [MSG_SITUACAO], id="clt"),
    pytest.param({COL_SITUACAO: "Contrato terceirizado"}, [MSG_SITUACAO], id="terceirizado"),
    pytest.param({COL_SITUACAO: "contrato clt"}, [], id="minusculo-nao-e-pego"),
]

_IFA = [
    pytest.param({COL_IFA: ""}, [MSG_ITINERARIO], id="vazio"),
    pytest.param({COL_IFA: "Ciências da Natureza"}, [MSG_ITINERARIO], id="preenchido"),
]

_TIPO_CURSO = [
    pytest.param({COL_TIPO_CURSO: ""}, [MSG_ITINERARIO], id="vazio"),
    pytest.param({COL_TIPO_CURSO: "Técnico"}, [MSG_ITINERARIO], id="preenchido"),
]

_COR = [
    pytest.param({COL_COR: "Não declarada"}, [MSG_COR], id="nao-declarada"),
    pytest.param({COL_COR: "não declarada"}, [], id="minusculo-nao-e-pego"),
]

_LOCALIZACAO = [
    pytest.param({COL_LOCALIZACAO: ""}, [MSG_LOCALIZACAO], id="vazia"),
    pytest.param({COL_LOCALIZACAO: "--"}, [], id="traco-nao-e-vazio"),
]

_LOCALIZACAO_DIF = [
    pytest.param({COL_LOCALIZACAO_DIF: ""}, [MSG_LOCALIZACAO_DIF], id="vazia"),
    pytest.param({COL_LOCALIZACAO_DIF: "--"}, [], id="traco-nao-e-vazio"),
]

_ANOS_FINAIS = [
    pytest.param({COL_ETAPA: ETAPAS_EF_6_9[0], COL_ESCOLARIDADE: "Ensino médio"},
                 [MSG_SUPERIOR], id="6-ano-sem-superior"),
    pytest.param({COL_ETAPA: ETAPAS_EF_6_9[1], COL_ESCOLARIDADE: "Ensino médio"},
                 [MSG_SUPERIOR], id="7-ano-sem-superior"),
    pytest.param({COL_ETAPA: ETAPAS_EF_6_9[2], COL_ESCOLARIDADE: "Ensino médio"},
                 [MSG_SUPERIOR], id="8-ano-sem-superior"),
    pytest.param({COL_ETAPA: ETAPAS_EF_6_9[3], COL_ESCOLARIDADE: "Ensino médio"},
                 [MSG_SUPERIOR], id="9-ano-sem-superior"),
    pytest.param({COL_ETAPA: "ENSINO FUNDAMENTAL DE 9 ANOS - 6º ANO",
                  COL_ESCOLARIDADE: "Ensino médio"},
                 [MSG_SUPERIOR], id="caixa-nao-importa"),
    pytest.param({COL_ETAPA: ETAPAS_EF_6_9[0], COL_ESCOLARIDADE: "Educação superior"},
                 [], id="superior-ok"),
    pytest.param({COL_ETAPA: "Ensino fundamental de 9 anos - 1º Ano",
                  COL_ESCOLARIDADE: "Ensino médio"},
                 [], id="1-ano-fora-do-escopo"),
]


@pytest.mark.parametrize("overrides,esperado", _SITUACAO)
def test_situacao(df, overrides, esperado):
    assert [r["erros"] for r in _validar(df, overrides)] == ([esperado] if esperado else [])


@pytest.mark.parametrize("overrides,esperado", _IFA)
def test_ifa(df, overrides, esperado):
    assert [r["erros"] for r in _validar(df, overrides)] == ([esperado] if esperado else [])


@pytest.mark.parametrize("overrides,esperado", _TIPO_CURSO)
def test_tipo_curso(df, overrides, esperado):
    assert [r["erros"] for r in _validar(df, overrides)] == ([esperado] if esperado else [])


@pytest.mark.parametrize("overrides,esperado", _COR)
def test_cor(df, overrides, esperado):
    assert [r["erros"] for r in _validar(df, overrides)] == ([esperado] if esperado else [])


@pytest.mark.parametrize("overrides,esperado", _LOCALIZACAO)
def test_localizacao(df, overrides, esperado):
    assert [r["erros"] for r in _validar(df, overrides)] == ([esperado] if esperado else [])


@pytest.mark.parametrize("overrides,esperado", _LOCALIZACAO_DIF)
def test_localizacao_diferenciada(df, overrides, esperado):
    assert [r["erros"] for r in _validar(df, overrides)] == ([esperado] if esperado else [])


@pytest.mark.parametrize("overrides,esperado", _ANOS_FINAIS)
def test_anos_finais(df, overrides, esperado):
    assert [r["erros"] for r in _validar(df, overrides)] == ([esperado] if esperado else [])
