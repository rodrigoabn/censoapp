"""Testes golden de `rules/unidades.py` — congelam o comportamento atual.

Cada regra nomeada tem caso positivo (molde válido) e negativo (uma célula
sobrescrita). As mensagens esperadas são copiadas do módulo de produção; se uma
regra deixar de encontrar a coluna (cabeçalho divergente), o negativo falha —
canário de fidelidade.

Observações pinadas:

- A coluna 0/1 de cada aba é lida **posicionalmente** como código INEP e nome
  da unidade (não pelo cabeçalho).
- Aba ausente: a primeira (`Vinculação institucional e Conv`) retorna um único
  erro; as demais anexam o erro e interrompem (early-return).
- Aba vazia (sem linhas de dados) interrompe a validação das abas seguintes.
- `Equipamentos e recursos tecnoló` é a única mensagem de aba ausente com
  "nao" sem acento (typo do módulo — comportamento congelado).
"""

from __future__ import annotations

from datetime import date

import pytest

from apps.verificacao_inconsistencias.src.rules.unidades import (
    SHEET_NAME,
    SHEET_NAME_EQUIP,
    SHEET_NAME_ESTRUTURA,
    SHEET_NAME_FUNC,
    SHEET_NAME_ORG,
    validate_unidades,
)

CODIGO = "33012345"
NOME = "Escola Teste"

# Cabeçalhos literais exatos do export (en-dash "–" e typos preservados).
H_REGULAMENTACAO = (
    "2 - Regulamentação/autorização no conselho ou órgão municipal, estadual ou federal de educação"
)
H_LOCALIZACAO = "3 – localizacaoZona"
H_PARCERIA = (
    "5 - A escola possui parceria ou convênio com a Administração Pública e/ou outras instituições"
)
H_SITUACAO = "6 - Situação de funcionamento"
H_7A = "7a – Início"
H_7B = "7b -Término (previsão)"
H_CEP = "9 - CEP"
H_DISTRITO = "11b – Distrito"
H_EMAIL = "19 - Endereço eletrônico (e-mail) da escola"
H_LOC_DIF = "20 - Localização diferenciada da escola"
H_PREDIO = "Prédio escolar"
H_OCUPACAO = "28 - Forma de ocupação do prédio escolar"
H_COMPARTILHA = "29 - A escola compartilha o seu prédio com outra instituição de ensino"
H_AGUA = "30 - Fornece água potável para o consumo humano"
H_DORMITORIO = "Dormitório de professor(a)"
H_LABORATORIO = "Laboratório específico para a educação profissional"
H_OFICINA = "Sala de oficinas da educação profissional"
H_COMPUTADORES = "Computadores"
H_SEM_INTERNET = "Não possui acesso à internet"
H_USO_ADMIN = "Para uso administrativo"
H_BANDA_LARGA = "47 - Internet banda larga"
H_ALIMENTACAO = "49 - A escola fornece alimentação escolar para os alunos"
H_INDIGENA = "50 - Escola indígena *"
H_EXAME = (
    "58 - A escola faz exame de seleção para ingresso de seus alunos "
    "(avaliação por prova e/ou análise curricular)"
)

TIPO_POR_ABA = {
    SHEET_NAME: "Vinculação institucional e Conv",
    SHEET_NAME_FUNC: "Funcionamento e Identificação",
    SHEET_NAME_ESTRUTURA: "Estrutura física",
    SHEET_NAME_EQUIP: "Equipamentos e recursos tecnoló",
    SHEET_NAME_ORG: "Organização escolar",
}


def _molde() -> dict[str, list[list]]:
    """Workbook 100% válido — as 5 abas, uma linha de dados cada."""
    return {
        SHEET_NAME: [
            ["Código do Inep", "Nome da Unidade", H_REGULAMENTACAO, "Estadual", "Municipal",
             H_LOCALIZACAO, H_PARCERIA],
            [CODIGO, NOME, "Sim", "", "Sim", "Urbana", "Não"],
        ],
        SHEET_NAME_FUNC: [
            ["Código do Inep", "Nome da Unidade", H_SITUACAO, H_7A, H_7B, H_CEP, H_DISTRITO,
             H_EMAIL, H_LOC_DIF],
            [CODIGO, NOME, "Em funcionamento", "", "", "50000-000", "Centro", "escola@teste.com",
             "Não se aplica"],
        ],
        SHEET_NAME_ESTRUTURA: [
            ["Código do Inep", "Nome da Unidade", H_PREDIO, H_OCUPACAO, H_COMPARTILHA, H_AGUA,
             H_DORMITORIO, H_LABORATORIO, H_OFICINA],
            [CODIGO, NOME, "Sim", "Próprio", "Não", "Sim", "", "", ""],
        ],
        SHEET_NAME_EQUIP: [
            ["Código do Inep", "Nome da Unidade", H_COMPUTADORES, H_SEM_INTERNET, H_USO_ADMIN,
             H_BANDA_LARGA],
            [CODIGO, NOME, "Sim", "", "Sim", "Sim"],
        ],
        SHEET_NAME_ORG: [
            ["Código do Inep", "Nome da Unidade", H_ALIMENTACAO, H_INDIGENA, H_EXAME],
            [CODIGO, NOME, "Oferece", "Não", "Não"],
        ],
    }


def _definir(abas: dict, aba: str, cabecalho: str, valor) -> dict:
    """Sobrescreve a célula da coluna `cabecalho` na linha de dados do molde."""
    linhas = abas[aba]
    idx = linhas[0].index(cabecalho)  # cabeçalho ausente = canário (ValueError)
    linhas[1][idx] = valor
    return abas


def test_arquivo_invalido_retorna_erro():
    resultados = validate_unidades(b"isto nao e um xlsx", [])
    assert len(resultados) == 1
    r = resultados[0]
    assert r["codigo_inep"] == ""
    assert r["nome_unidade"] == ""
    assert r["tipo_validacao"] == "unidades"
    assert r["status"] == "erro"
    assert r["detalhes"].startswith("Não foi possível ler o arquivo: ")


def test_molde_valido_sem_datas(wb_bytes):
    assert validate_unidades(wb_bytes(_molde()), []) == []


def test_molde_valido_com_datas_coincidentes(wb_bytes):
    abas = _molde()
    _definir(abas, SHEET_NAME_FUNC, H_7A, "01/02/2026")
    _definir(abas, SHEET_NAME_FUNC, H_7B, "20/12/2026")
    resultados = validate_unidades(wb_bytes(abas), [], date(2026, 2, 1), date(2026, 12, 20))
    assert resultados == []


def test_aba_vinculacao_ausente(wb_bytes):
    abas = _molde()
    del abas[SHEET_NAME]
    resultados = validate_unidades(wb_bytes(abas), [])
    assert resultados == [{
        "codigo_inep": "",
        "nome_unidade": "",
        "tipo_validacao": "unidades",
        "status": "erro",
        "detalhes": f"Aba '{SHEET_NAME}' não encontrada no arquivo.",
    }]


@pytest.mark.parametrize(
    "aba",
    [SHEET_NAME_FUNC, SHEET_NAME_ESTRUTURA, SHEET_NAME_EQUIP, SHEET_NAME_ORG],
    ids=["funcionamento", "estrutura", "equipamentos", "organizacao"],
)
def test_aba_ausente_anexa_erro(wb_bytes, aba):
    abas = _molde()
    del abas[aba]
    resultados = validate_unidades(wb_bytes(abas), [])
    assert len(resultados) == 1
    r = resultados[0]
    assert r["tipo_validacao"] == TIPO_POR_ABA[aba]
    assert r["status"] == "erro"
    # "Equipamentos" é a única aba com "nao" sem acento (typo do módulo).
    if aba == SHEET_NAME_EQUIP:
        esperado = f"Aba '{aba}' nao encontrada no arquivo."
    else:
        esperado = f"Aba '{aba}' não encontrada no arquivo."
    assert r["detalhes"] == esperado


def test_aba_ausente_interrompe_validacao_das_seguintes(wb_bytes):
    abas = _molde()
    del abas[SHEET_NAME_FUNC]
    _definir(abas, SHEET_NAME_ESTRUTURA, H_PREDIO, "Não")  # violação nunca vista
    resultados = validate_unidades(wb_bytes(abas), [])
    assert len(resultados) == 1
    assert resultados[0]["detalhes"] == f"Aba '{SHEET_NAME_FUNC}' não encontrada no arquivo."


def test_aba_vazia_interrompe_validacao_das_seguintes(wb_bytes):
    abas = _molde()
    abas[SHEET_NAME_FUNC] = [abas[SHEET_NAME_FUNC][0]]  # só cabeçalho
    _definir(abas, SHEET_NAME_ESTRUTURA, H_PREDIO, "Não")  # violação nunca vista
    assert validate_unidades(wb_bytes(abas), []) == []


def test_multiplas_violacoes_na_mesma_linha(wb_bytes):
    abas = _molde()
    _definir(abas, SHEET_NAME, H_REGULAMENTACAO, "Não")
    _definir(abas, SHEET_NAME, "Estadual", "PE")
    _definir(abas, SHEET_NAME, "Municipal", "")
    resultados = validate_unidades(wb_bytes(abas), [])
    assert [r["detalhes"] for r in resultados] == [
        f"Coluna '{H_REGULAMENTACAO}': esperado 'Sim', encontrado 'Não'",
        "Coluna 'Estadual': esperado vazio, encontrado 'PE'",
        "Coluna 'Municipal': esperado 'Sim', encontrado ''",
    ]
    for r in resultados:
        assert r["codigo_inep"] == CODIGO
        assert r["nome_unidade"] == NOME
        assert r["tipo_validacao"] == TIPO_POR_ABA[SHEET_NAME]
        assert r["status"] == "inconsistente"


def test_aceitacao_insensivel_a_caixa_e_acento(wb_bytes):
    abas = _molde()
    _definir(abas, SHEET_NAME, H_REGULAMENTACAO, "SIM")
    _definir(abas, SHEET_NAME, H_PARCERIA, "NAO")
    _definir(abas, SHEET_NAME_ORG, H_INDIGENA, "nao")
    assert validate_unidades(wb_bytes(abas), []) == []


def test_valor_numerico_vira_texto(wb_bytes):
    abas = _definir(_molde(), SHEET_NAME, "Estadual", 123)
    resultados = validate_unidades(wb_bytes(abas), [])
    assert [r["detalhes"] for r in resultados] == [
        "Coluna 'Estadual': esperado vazio, encontrado '123'"
    ]


def test_codigo_e_nome_lidos_por_posicao(wb_bytes):
    """As colunas 0/1 trazem código e nome por posição — os cabeçalhos não importam."""
    abas = _molde()
    for linhas in abas.values():
        linhas[0][0] = "Nº"
        linhas[0][1] = "Escola"
    _definir(abas, SHEET_NAME, H_REGULAMENTACAO, "Não")
    resultados = validate_unidades(wb_bytes(abas), [])
    assert [r["detalhes"] for r in resultados] == [
        f"Coluna '{H_REGULAMENTACAO}': esperado 'Sim', encontrado 'Não'",
    ]
    assert resultados[0]["codigo_inep"] == CODIGO
    assert resultados[0]["nome_unidade"] == NOME


_NEGATIVOS = [
    # ── Vinculação institucional e Conv ──────────────────────────────
    pytest.param(
        SHEET_NAME, H_REGULAMENTACAO, "Não",
        f"Coluna '{H_REGULAMENTACAO}': esperado 'Sim', encontrado 'Não'",
        None, None, id="regulamentacao"),
    pytest.param(
        SHEET_NAME, "Estadual", "PE",
        "Coluna 'Estadual': esperado vazio, encontrado 'PE'",
        None, None, id="estadual-preenchida"),
    pytest.param(
        SHEET_NAME, "Municipal", "Não",
        "Coluna 'Municipal': esperado 'Sim', encontrado 'Não'",
        None, None, id="municipal"),
    pytest.param(
        SHEET_NAME, H_LOCALIZACAO, "",
        "Coluna '3 – localizacaoZona': não pode estar vazia",
        None, None, id="localizacao-vazia"),
    pytest.param(
        SHEET_NAME, H_PARCERIA, "Sim",
        f"Coluna '{H_PARCERIA}': esperado 'Não', encontrado 'Sim'",
        None, None, id="parceria"),
    # ── Funcionamento e Identificação ────────────────────────────────
    pytest.param(
        SHEET_NAME_FUNC, H_SITUACAO, "",
        "Coluna '6 - Situação de funcionamento': não pode estar vazia",
        None, None, id="situacao-vazia"),
    pytest.param(
        SHEET_NAME_FUNC, H_7A, "31/01/2026",
        "Coluna '7a – Início': esperado '01/02/2026', encontrado '31/01/2026'",
        date(2026, 2, 1), None, id="7a-divergente"),
    pytest.param(
        SHEET_NAME_FUNC, H_7B, "19/12/2026",
        "Coluna '7b -Término (previsão)': esperado '20/12/2026', encontrado '19/12/2026'",
        None, date(2026, 12, 20), id="7b-divergente"),
    pytest.param(
        SHEET_NAME_FUNC, H_CEP, "",
        "Coluna '9 - CEP': não pode estar vazia",
        None, None, id="cep-vazio"),
    pytest.param(
        SHEET_NAME_FUNC, H_DISTRITO, "",
        "Coluna '11b – Distrito': não pode estar vazia",
        None, None, id="distrito-vazio"),
    pytest.param(
        SHEET_NAME_FUNC, H_EMAIL, "",
        "Coluna '19 - Endereço eletrônico (e-mail) da escola': não pode estar vazia",
        None, None, id="email-vazio"),
    pytest.param(
        SHEET_NAME_FUNC, H_LOC_DIF, "",
        "Coluna '20 - Localização diferenciada da escola': não pode estar vazia",
        None, None, id="localizacao-dif-vazia"),
    # ── Estrutura física ─────────────────────────────────────────────
    pytest.param(
        SHEET_NAME_ESTRUTURA, H_PREDIO, "Não",
        "Coluna 'Prédio escolar': esperado 'Sim', encontrado 'Não'",
        None, None, id="predio"),
    pytest.param(
        SHEET_NAME_ESTRUTURA, H_OCUPACAO, "",
        "Coluna '28 - Forma de ocupação do prédio escolar': não pode estar vazia",
        None, None, id="ocupacao-vazia"),
    pytest.param(
        SHEET_NAME_ESTRUTURA, H_COMPARTILHA, "",
        "Coluna '29 - A escola compartilha o seu prédio com outra instituição de ensino': "
        "não pode estar vazia",
        None, None, id="compartilha-vazia"),
    pytest.param(
        SHEET_NAME_ESTRUTURA, H_AGUA, "",
        "Coluna '30 - Fornece água potável para o consumo humano': não pode estar vazia",
        None, None, id="agua-vazia"),
    pytest.param(
        SHEET_NAME_ESTRUTURA, H_DORMITORIO, "Sim",
        "Coluna 'Dormitório de professor(a)': esperado vazio, encontrado 'Sim'",
        None, None, id="dormitorio-preenchido"),
    pytest.param(
        SHEET_NAME_ESTRUTURA, H_LABORATORIO, "Sim",
        "Coluna 'Laboratório específico para a educação profissional': "
        "esperado vazio, encontrado 'Sim'",
        None, None, id="laboratorio-preenchido"),
    pytest.param(
        SHEET_NAME_ESTRUTURA, H_OFICINA, "Sim",
        "Coluna 'Sala de oficinas da educação profissional': esperado vazio, encontrado 'Sim'",
        None, None, id="oficina-preenchida"),
    # ── Equipamentos e recursos tecnoló ──────────────────────────────
    pytest.param(
        SHEET_NAME_EQUIP, H_COMPUTADORES, "Não",
        "Coluna 'Computadores': esperado 'Sim', encontrado 'Não'",
        None, None, id="computadores"),
    pytest.param(
        SHEET_NAME_EQUIP, H_SEM_INTERNET, "Sim",
        "Coluna 'Não possui acesso à internet': deve estar vazia",
        None, None, id="sem-internet-preenchida"),
    pytest.param(
        SHEET_NAME_EQUIP, H_USO_ADMIN, "Não",
        "Coluna 'Para uso administrativo': esperado 'Sim', encontrado 'Não'",
        None, None, id="uso-admin"),
    pytest.param(
        SHEET_NAME_EQUIP, H_BANDA_LARGA, "Não",
        "Coluna '47 - Internet banda larga': esperado 'Sim', encontrado 'Não'",
        None, None, id="banda-larga"),
    # ── Organização escolar ──────────────────────────────────────────
    pytest.param(
        SHEET_NAME_ORG, H_ALIMENTACAO, "Não oferece",
        "Coluna '49 - A escola fornece alimentação escolar para os alunos': "
        "diferentes de 'Oferece', encontrado 'Não oferece'",
        None, None, id="alimentacao"),
    pytest.param(
        SHEET_NAME_ORG, H_INDIGENA, "Sim",
        "Coluna '50 - Escola indígena *': esperado 'Não', encontrado 'Sim'",
        None, None, id="indigena"),
    pytest.param(
        SHEET_NAME_ORG, H_EXAME, "Sim",
        "Coluna '58 - A escola faz exame de seleção para ingresso de seus alunos "
        "(avaliação por prova e/ou análise curricular)': esperado 'Não', encontrado 'Sim'",
        None, None, id="exame"),
]


@pytest.mark.parametrize("aba,cabecalho,valor,esperado,inicio,termino", _NEGATIVOS)
def test_regra_negativa(wb_bytes, aba, cabecalho, valor, esperado, inicio, termino):
    abas = _definir(_molde(), aba, cabecalho, valor)
    resultados = validate_unidades(wb_bytes(abas), [], inicio, termino)
    assert len(resultados) == 1, resultados
    (r,) = resultados
    assert r["codigo_inep"] == CODIGO
    assert r["nome_unidade"] == NOME
    assert r["tipo_validacao"] == TIPO_POR_ABA[aba]
    assert r["status"] == "inconsistente"
    assert r["detalhes"] == esperado
