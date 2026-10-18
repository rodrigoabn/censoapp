"""Testes golden de `src/validations.py` — o registro central das validações.

Pina a estrutura do `VALIDATIONS`: ordem das chaves (ordem da navegação),
contrato de cada entrada (`key`, `state_prefix`, `requires_dates`, `title`,
`subtitle`, `validate`), origem (`source`) e flags de divisão por tipo de
planilha. O caso mais delicado é `expected_columns`: a checagem de estrutura do
upload usa essa lista como referência — uma coluna consumida pelos validadores
mas ausente dela produz falso alarme para o usuário; por isso o teste afirma
que ela **contém** todas as colunas que cada validador lê.

Observações pinadas:

- Os chamáveis são comparados por identidade (`is`): o registro deve apontar
  exatamente para as funções cobertas pelos outros arquivos desta pasta.
- `validate` de turmas recebe a assinatura estendida; por isso a comparação por
  identidade vale para todas as entradas.
- As colunas consumidas por `turmas.py` que não são constantes públicas do
  módulo estão listadas aqui como retrato (snapshot) do consumo atual.
"""

from __future__ import annotations

import pytest

from apps.verificacao_inconsistencias.src.rules import (
    aluno,
    extrair_alunos_sem_cpf,
    find_matriculas_duplicadas,
    levantamento_cor_raca,
    profissionais,
    turmas,
    validate_aluno,
    validate_gestor,
    validate_profissionais,
    validate_turmas,
    validate_unidades,
)
from apps.verificacao_inconsistencias.src.validations import VALIDATIONS

_SPLIT_FLAGS = ("split_tipo_turma", "split_aluno", "split_profissionais")

_ENTRADAS = [
    pytest.param(
        "unidades", validate_unidades, "vu_", True,
        "Inconsistências no Cadastro de Unidades",
        "Verifica inconsistências nos dados cadastrais das unidades escolares no Educacenso.",
        id="unidades",
    ),
    pytest.param(
        "gestor", validate_gestor, "vg_", False,
        "Inconsistências no Cadastro de Gestor",
        "Verifica inconsistências nos dados cadastrais do gestor escolar no Educacenso.",
        id="gestor",
    ),
    pytest.param(
        "turmas", validate_turmas, "vt_", False,
        "Inconsistências no Cadastro de Turmas",
        "Verifica inconsistências nos dados das turmas declaradas no Educacenso.",
        id="turmas",
    ),
    pytest.param(
        "aluno", validate_aluno, "va_", False,
        "Inconsistências no Cadastro de Aluno",
        "Verifica inconsistências nos dados dos alunos declarados no Educacenso.",
        id="aluno",
    ),
    pytest.param(
        "profissionais", validate_profissionais, "vp_", False,
        "Inconsistências no Cadastro de Profissionais Escolares",
        "Verifica inconsistências nos dados dos profissionais escolares declarados no Educacenso.",
        id="profissionais",
    ),
]


def test_ordem_das_chaves():
    assert list(VALIDATIONS) == ["unidades", "gestor", "turmas", "aluno", "profissionais"]


@pytest.mark.parametrize(
    "chave,validate,prefixo,requires_dates,titulo,subtitulo", _ENTRADAS
)
def test_contrato_da_entrada(chave, validate, prefixo, requires_dates, titulo, subtitulo):
    entrada = VALIDATIONS[chave]
    assert entrada["key"] == chave
    assert entrada["validate"] is validate
    assert entrada["state_prefix"] == prefixo
    assert entrada["requires_dates"] is requires_dates
    assert entrada["title"] == titulo
    assert entrada["subtitle"] == subtitulo


@pytest.mark.parametrize("chave,source,splits", [
    pytest.param("unidades", None, set(), id="unidades"),
    pytest.param("gestor", None, set(), id="gestor"),
    pytest.param("turmas", "zip", {"split_tipo_turma"}, id="turmas"),
    pytest.param("aluno", "zip", {"split_aluno"}, id="aluno"),
    pytest.param("profissionais", "zip", {"split_profissionais"}, id="profissionais"),
])
def test_source_e_flags_de_divisao(chave, source, splits):
    entrada = VALIDATIONS[chave]
    assert entrada.get("source") == source
    presentes = {flag for flag in _SPLIT_FLAGS if entrada.get(flag) is True}
    assert presentes == splits


@pytest.mark.parametrize("chave,tem_expected", [
    pytest.param("unidades", False, id="unidades"),
    pytest.param("gestor", False, id="gestor"),
    pytest.param("turmas", True, id="turmas"),
    pytest.param("aluno", True, id="aluno"),
    pytest.param("profissionais", True, id="profissionais"),
])
def test_expected_columns_apenas_nos_zip(chave, tem_expected):
    entrada = VALIDATIONS[chave]
    assert ("expected_columns" in entrada) is tem_expected
    if tem_expected:
        colunas = entrada["expected_columns"]
        assert isinstance(colunas, list) and colunas
        assert len(colunas) == len(set(colunas)), "expected_columns com duplicatas"


def test_auxiliares_exclusivos_do_aluno():
    entrada = VALIDATIONS["aluno"]
    assert entrada["find_duplicadas"] is find_matriculas_duplicadas
    assert entrada["levantamento_cor_raca"] is levantamento_cor_raca
    assert entrada["extrair_sem_cpf"] is extrair_alunos_sem_cpf
    for chave in ("unidades", "gestor", "turmas", "profissionais"):
        for auxiliar in ("find_duplicadas", "levantamento_cor_raca", "extrair_sem_cpf"):
            assert auxiliar not in VALIDATIONS[chave]


def _colunas_consumidas_por(chave: str) -> set[str]:
    if chave == "turmas":
        return {
            # `_validar_linha` (curricular)
            "Tipo de turma",
            "Nome da turma",
            "Etapa Agregada",
            "Formas de organização da turma",
            "Etapa de ensino",
            "Carga horária semanal (hh:mm)",
            "Dias da semana e horário de funcionamento",
            "Áreas do conhecimento/componentes curriculares",
            *turmas._COLS_ESPECIAIS,
            # `_validar_escolarizacao` reusa "Nome da turma", "Etapa Agregada",
            # "Etapa de ensino" e "Carga horária semanal (hh:mm)".
        }
    if chave == "aluno":
        return {
            aluno.COL_CPF,
            aluno.COL_IDENTIFICACAO,
            aluno.COL_NOME,
            aluno.COL_MATRICULA,
            aluno.COL_TURMA,
            aluno.COL_NOME_TURMA,
            aluno.COL_NASCIMENTO,
            aluno.COL_LOCALIZACAO,
            aluno.COL_TRANSPORTE,
            aluno.COL_PODER_PUBLICO,
            aluno.COL_ETAPA_ENSINO,
            aluno.COL_COR_RACA,
        }
    if chave == "profissionais":
        return {
            profissionais.COL_SITUACAO,
            profissionais.COL_IDENTIFICACAO,
            profissionais.COL_IFA,
            profissionais.COL_TIPO_CURSO,
            profissionais.COL_COR,
            profissionais.COL_LOCALIZACAO,
            profissionais.COL_LOCALIZACAO_DIF,
            profissionais.COL_ESCOLARIDADE,
            profissionais.COL_ETAPA,
            profissionais.COL_FUNCAO,
        }
    raise AssertionError(f"chave sem snapshot de colunas: {chave}")


@pytest.mark.parametrize("chave", ["turmas", "aluno", "profissionais"])
def test_expected_columns_cobrem_colunas_consumidas(chave):
    entrada = VALIDATIONS[chave]
    faltando = _colunas_consumidas_por(chave) - set(entrada["expected_columns"])
    assert not faltando, f"colunas consumidas fora de expected_columns: {sorted(faltando)}"
