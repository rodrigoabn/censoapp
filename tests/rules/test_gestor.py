"""Testes golden de `rules/gestor.py` — congelam o comportamento atual.

Cada regra nomeada tem caso positivo (molde válido) e negativo (uma célula
sobrescrita). As mensagens esperadas são copiadas do módulo de produção; se uma
regra deixar de encontrar a coluna (cabeçalho divergente), o negativo falha —
canário de fidelidade.

Observações pinadas:

- A coluna 0/1 de cada aba é lida **posicionalmente** como código INEP e nome
  da unidade (não pelo cabeçalho).
- Aba ausente: `Vínculo do gestor` retorna um único erro; as demais anexam o
  erro e interrompem (early-return).
- Aba **vazia** (sem linhas de dados) **não** interrompe as seguintes — ao
  contrário de `unidades.py`. As regras da aba vazia simplesmente não rodam.
- O critério de acesso é comparado **sem** normalização de caixa (`v in {...}`):
  o mesmo texto em minúsculas não é capturado (quirk congelado).
"""

from __future__ import annotations

import pytest

from apps.verificacao_inconsistencias.src.rules.gestor import (
    SHEET_DADOS,
    SHEET_IDENT,
    SHEET_VINCULO,
    validate_gestor,
)

CODIGO = "33012345"
NOME = "Escola Teste"

H_CARGO = "1 – Cargo"
H_ACESSO = "2 - Critério de acesso ao cargo/função"
H_VINCULO = "3 - Situação Funcional/Regime de contratação/Tipo de vínculo"
H_EMAIL = "Email principal"
H_FILIACAO1 = "5a - Nome completo da filiação 1"
H_FILIACAO2 = "5b - Nome completo da filiação 2"
H_SEXO = "6 – Sexo"
H_COR = "7 – Cor/Raça"
H_NACIONALIDADE = "8 – Nacionalidade"
H_UF_NASC = "10 - UF de nascimento"
H_MUNICIPIO_NASC = "11 - Município de nascimento"
H_PAIS = "13 - País de residência"
H_CEP = "14 – CEP"
H_UF = "15 – UF"
H_MUNICIPIO = "16 – Município"
H_ZONA = "17 - Localização/zona de residência"
H_LOC_DIF = "18 - Localização diferenciada da residência"
H_ESCOLARIDADE = "19 - Maior nível de escolaridade concluído"
H_ENSINO_MEDIO = "19a - Tipo de ensino médio cursado"
H_POS = "20. Pós-graduações concluídas"

PROIBIDO_ELEITORAL = (
    "Exclusivamente por processo eleitoral com a participação da comunidade escolar"
)
PROIBIDO_CONCURSO = "Concurso público específico para o cargo de gestor escolar"


def _molde() -> dict[str, list[list]]:
    """Workbook 100% válido — as 3 abas, uma linha de dados cada."""
    return {
        SHEET_VINCULO: [
            ["Código do Inep", "Nome da Unidade", H_CARGO, H_ACESSO, H_VINCULO, H_EMAIL],
            [CODIGO, NOME, "Diretor(a)", "Indicação", "Concursado/efetivo/estável",
             "gestor@teste.com"],
        ],
        SHEET_IDENT: [
            ["Código do Inep", "Nome da Unidade", H_FILIACAO1, H_FILIACAO2, H_SEXO, H_COR,
             H_NACIONALIDADE, H_UF_NASC, H_MUNICIPIO_NASC],
            [CODIGO, NOME, "Maria", "João", "Feminino", "Parda", "Brasileira", "PE", "Recife"],
        ],
        SHEET_DADOS: [
            ["Código do Inep", "Nome da Unidade", H_PAIS, H_CEP, H_UF, H_MUNICIPIO, H_ZONA,
             H_LOC_DIF, H_ESCOLARIDADE, H_ENSINO_MEDIO, H_POS],
            [CODIGO, NOME, "Brasil", "50000-000", "PE", "Recife", "Urbana", "Não",
             "Educação superior", "Médio", "Não"],
        ],
    }


def _definir(abas: dict, aba: str, cabecalho: str, valor) -> dict:
    """Sobrescreve a célula da coluna `cabecalho` na linha de dados do molde."""
    linhas = abas[aba]
    idx = linhas[0].index(cabecalho)  # cabeçalho ausente = canário (ValueError)
    linhas[1][idx] = valor
    return abas


def test_arquivo_invalido_retorna_erro():
    resultados = validate_gestor(b"isto nao e um xlsx", [])
    assert len(resultados) == 1
    r = resultados[0]
    assert r["codigo_inep"] == ""
    assert r["nome_unidade"] == ""
    assert r["tipo_validacao"] == "gestor"
    assert r["status"] == "erro"
    assert r["detalhes"].startswith("Não foi possível ler o arquivo: ")


def test_molde_valido(wb_bytes):
    assert validate_gestor(wb_bytes(_molde()), []) == []


def test_aba_vinculo_ausente(wb_bytes):
    abas = _molde()
    del abas[SHEET_VINCULO]
    resultados = validate_gestor(wb_bytes(abas), [])
    assert resultados == [{
        "codigo_inep": "",
        "nome_unidade": "",
        "tipo_validacao": "gestor",
        "status": "erro",
        "detalhes": f"Aba '{SHEET_VINCULO}' não encontrada no arquivo.",
    }]


@pytest.mark.parametrize("aba", [SHEET_IDENT, SHEET_DADOS], ids=["identificacao", "dados"])
def test_aba_ausente_anexa_erro(wb_bytes, aba):
    abas = _molde()
    del abas[aba]
    resultados = validate_gestor(wb_bytes(abas), [])
    assert len(resultados) == 1
    r = resultados[0]
    assert r["codigo_inep"] == ""
    assert r["nome_unidade"] == ""
    assert r["tipo_validacao"] == aba
    assert r["status"] == "erro"
    assert r["detalhes"] == f"Aba '{aba}' não encontrada no arquivo."


def test_aba_ausente_interrompe_validacao_das_seguintes(wb_bytes):
    abas = _molde()
    del abas[SHEET_IDENT]
    _definir(abas, SHEET_DADOS, H_PAIS, "")  # violação nunca vista
    resultados = validate_gestor(wb_bytes(abas), [])
    assert len(resultados) == 1
    assert resultados[0]["detalhes"] == f"Aba '{SHEET_IDENT}' não encontrada no arquivo."


def test_aba_vinculo_vazia_nao_interrompe_as_seguintes(wb_bytes):
    abas = _molde()
    abas[SHEET_VINCULO] = [abas[SHEET_VINCULO][0]]  # só cabeçalho
    _definir(abas, SHEET_IDENT, H_SEXO, "")
    resultados = validate_gestor(wb_bytes(abas), [])
    assert [r["detalhes"] for r in resultados] == [
        "Coluna '6 – Sexo': não pode estar vazia"
    ]
    assert resultados[0]["tipo_validacao"] == SHEET_IDENT


def test_multiplas_violacoes_na_mesma_linha(wb_bytes):
    abas = _molde()
    _definir(abas, SHEET_VINCULO, H_CARGO, "Coordenador(a)")
    _definir(abas, SHEET_VINCULO, H_ACESSO, "")
    _definir(abas, SHEET_VINCULO, H_EMAIL, "")
    resultados = validate_gestor(wb_bytes(abas), [])
    assert [r["detalhes"] for r in resultados] == [
        "Coluna '1 – Cargo': esperado 'Diretor(a)', encontrado 'Coordenador(a)'",
        "Coluna '2 - Critério de acesso ao cargo/função': não pode estar vazia",
        "Coluna 'Email principal': não pode estar vazia",
    ]
    for r in resultados:
        assert r["codigo_inep"] == CODIGO
        assert r["nome_unidade"] == NOME
        assert r["tipo_validacao"] == SHEET_VINCULO
        assert r["status"] == "inconsistente"


def test_aceitacao_insensivel_a_caixa(wb_bytes):
    abas = _molde()
    _definir(abas, SHEET_VINCULO, H_CARGO, "DIRETOR(A)")
    _definir(abas, SHEET_VINCULO, H_VINCULO, "CONTRATO TEMPORÁRIO")
    _definir(abas, SHEET_IDENT, H_COR, "PARDA")
    _definir(abas, SHEET_DADOS, H_ESCOLARIDADE, "EDUCAÇÃO SUPERIOR")
    assert validate_gestor(wb_bytes(abas), []) == []


def test_criterio_proibido_exige_caixa_exata(wb_bytes):
    # A comparação é `v in {...}` sem `.lower()`: minúsculas não são capturadas.
    abas = _definir(_molde(), SHEET_VINCULO, H_ACESSO, PROIBIDO_ELEITORAL.lower())
    assert validate_gestor(wb_bytes(abas), []) == []


def test_codigo_e_nome_lidos_por_posicao(wb_bytes):
    """As colunas 0/1 trazem código e nome por posição — os cabeçalhos não importam."""
    abas = _molde()
    for linhas in abas.values():
        linhas[0][0] = "Nº"
        linhas[0][1] = "Escola"
    _definir(abas, SHEET_VINCULO, H_ACESSO, PROIBIDO_ELEITORAL)
    resultados = validate_gestor(wb_bytes(abas), [])
    assert len(resultados) == 1
    (r,) = resultados
    assert r["codigo_inep"] == CODIGO
    assert r["nome_unidade"] == NOME


_NEGATIVOS = [
    # ── Vínculo do gestor ────────────────────────────────────────────
    pytest.param(
        SHEET_VINCULO, H_CARGO, "Coordenador(a)",
        "Coluna '1 – Cargo': esperado 'Diretor(a)', encontrado 'Coordenador(a)'",
        id="cargo"),
    pytest.param(
        SHEET_VINCULO, H_ACESSO, "",
        "Coluna '2 - Critério de acesso ao cargo/função': não pode estar vazia",
        id="acesso-vazio"),
    pytest.param(
        SHEET_VINCULO, H_ACESSO, PROIBIDO_ELEITORAL,
        f"Coluna '2 - Critério de acesso ao cargo/função': valor não permitido '{PROIBIDO_ELEITORAL}'",
        id="acesso-proibido-eleitoral"),
    pytest.param(
        SHEET_VINCULO, H_ACESSO, PROIBIDO_CONCURSO,
        f"Coluna '2 - Critério de acesso ao cargo/função': valor não permitido '{PROIBIDO_CONCURSO}'",
        id="acesso-proibido-concurso"),
    pytest.param(
        SHEET_VINCULO, H_VINCULO, "Comissionado",
        "Coluna '3 - Situação Funcional/Regime de contratação/Tipo de vínculo': esperado "
        "'Concursado/efetivo/estável' ou 'Contrato temporário', encontrado 'Comissionado'",
        id="vinculo"),
    pytest.param(
        SHEET_VINCULO, H_EMAIL, "",
        "Coluna 'Email principal': não pode estar vazia",
        id="email-vazio"),
    # ── Identificação ────────────────────────────────────────────────
    pytest.param(
        SHEET_IDENT, H_FILIACAO1, "",
        "Coluna '5a - Nome completo da filiação 1': não pode estar vazia",
        id="filiacao1-vazia"),
    pytest.param(
        SHEET_IDENT, H_FILIACAO2, "",
        "Coluna '5b - Nome completo da filiação 2': não pode estar vazia",
        id="filiacao2-vazia"),
    pytest.param(
        SHEET_IDENT, H_SEXO, "",
        "Coluna '6 – Sexo': não pode estar vazia",
        id="sexo-vazio"),
    pytest.param(
        SHEET_IDENT, H_COR, "Não declarada",
        "Coluna '7 – Cor/Raça': não pode ser 'Não declarada', encontrado 'Não declarada'",
        id="cor-nao-declarada"),
    pytest.param(
        SHEET_IDENT, H_COR, "nao declarada",
        "Coluna '7 – Cor/Raça': não pode ser 'Não declarada', encontrado 'nao declarada'",
        id="cor-nao-declarada-sem-acento"),
    pytest.param(
        SHEET_IDENT, H_NACIONALIDADE, "",
        "Coluna '8 – Nacionalidade': não pode estar vazia",
        id="nacionalidade-vazia"),
    pytest.param(
        SHEET_IDENT, H_UF_NASC, "",
        "Coluna '10 - UF de nascimento': não pode estar vazia",
        id="uf-nascimento-vazia"),
    pytest.param(
        SHEET_IDENT, H_MUNICIPIO_NASC, "",
        "Coluna '11 - Município de nascimento': não pode estar vazia",
        id="municipio-nascimento-vazio"),
    # ── Dados pessoais ───────────────────────────────────────────────
    pytest.param(
        SHEET_DADOS, H_PAIS, "",
        "Coluna '13 - País de residência': não pode estar vazia",
        id="pais-vazio"),
    pytest.param(
        SHEET_DADOS, H_CEP, "",
        "Coluna '14 – CEP': não pode estar vazia",
        id="cep-vazio"),
    pytest.param(
        SHEET_DADOS, H_UF, "",
        "Coluna '15 – UF': não pode estar vazia",
        id="uf-vazia"),
    pytest.param(
        SHEET_DADOS, H_MUNICIPIO, "",
        "Coluna '16 – Município': não pode estar vazia",
        id="municipio-vazio"),
    pytest.param(
        SHEET_DADOS, H_ZONA, "",
        "Coluna '17 - Localização/zona de residência': não pode estar vazia",
        id="zona-vazia"),
    pytest.param(
        SHEET_DADOS, H_LOC_DIF, "",
        "Coluna '18 - Localização diferenciada da residência': não pode estar vazia",
        id="localizacao-dif-vazia"),
    pytest.param(
        SHEET_DADOS, H_ESCOLARIDADE, "Ensino médio",
        "Coluna '19 - Maior nível de escolaridade concluído': esperado 'Educação superior', "
        "encontrado 'Ensino médio'",
        id="escolaridade"),
    pytest.param(
        SHEET_DADOS, H_ENSINO_MEDIO, "",
        "Coluna '19a - Tipo de ensino médio cursado': não pode estar vazia",
        id="ensino-medio-vazio"),
    pytest.param(
        SHEET_DADOS, H_POS, "",
        "Coluna '20. Pós-graduações concluídas': não pode estar vazia",
        id="pos-graduacoes-vazias"),
]


@pytest.mark.parametrize("aba,cabecalho,valor,esperado", _NEGATIVOS)
def test_regra_negativa(wb_bytes, aba, cabecalho, valor, esperado):
    abas = _definir(_molde(), aba, cabecalho, valor)
    resultados = validate_gestor(wb_bytes(abas), [])
    assert len(resultados) == 1, resultados
    (r,) = resultados
    assert r["codigo_inep"] == CODIGO
    assert r["nome_unidade"] == NOME
    assert r["tipo_validacao"] == aba
    assert r["status"] == "inconsistente"
    assert r["detalhes"] == esperado
