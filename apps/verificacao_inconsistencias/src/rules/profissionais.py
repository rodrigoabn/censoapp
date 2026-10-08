from __future__ import annotations

import pandas as pd

COL_SITUACAO = "Situação Funcional / Regime de contratação / Tipo de vínculo"
COL_IDENTIFICACAO = "Identificação única"
COL_IFA = "Área(s) do Itinerário formativo que leciona (IFA)"
COL_TIPO_CURSO = "Tipo do curso do itinerário de formação técnica e profissional que leciona"
COL_COR = "Cor/Raça"
COL_LOCALIZACAO = "Localização/Zona de residência"
COL_LOCALIZACAO_DIF = "Localização diferenciada de residência"
COL_ESCOLARIDADE = "Maior nível de escolaridade concluído"
COL_ETAPA = "Etapa de ensino"
COL_FUNCAO = "Função que exerce na turma"
FUNCAO_APOIO = "Profissional de apoio escolar para alunos com deficiência (Lei 13.146/2015)"

SITUACOES_PROIBIDAS = {"Contrato CLT", "Contrato terceirizado"}

ETAPAS_EF_6_9 = [
    "Ensino fundamental de 9 anos - 6º Ano",
    "Ensino fundamental de 9 anos - 7º Ano",
    "Ensino fundamental de 9 anos - 8º Ano",
    "Ensino fundamental de 9 anos - 9º Ano",
]


def _contem(texto: str, busca: str) -> bool:
    return busca.lower() in (texto or "").lower()


def _validar_linha(row: pd.Series) -> list[tuple[str, str]]:
    erros: list[tuple[str, str]] = []

    def get(col: str) -> str:
        v = row.get(col)
        return "" if v is None else str(v).strip()

    situacao = get(COL_SITUACAO)
    if situacao in SITUACOES_PROIBIDAS:
        erros.append(("situacao", "Situação Funcional informada como 'Contrato CLT ou Terceirizado informado'"))

    if get(COL_IFA) != "-":
        erros.append(("ifa", "Itinerário formativo não deve ser informado"))

    if get(COL_TIPO_CURSO) != "-":
        erros.append(("tipo_curso", "Itinerário formativo não deve ser informado"))

    if get(COL_COR) == "Não declarada":
        erros.append(("cor", "Etnia informada como Não Declarado"))

    if not get(COL_LOCALIZACAO):
        erros.append(("localizacao", "Zona da residência não informada"))

    if not get(COL_LOCALIZACAO_DIF):
        erros.append(("localizacao_dif", "Localização diferenciada não informada"))

    is_apoio = get(COL_FUNCAO).strip() == FUNCAO_APOIO

    escolaridade = get(COL_ESCOLARIDADE)
    if not is_apoio and escolaridade == "Ensino fundamental":
        erros.append(("escolaridade_fund", "Escolarização do Profissional informada como Ensino fundamental"))

    etapa = get(COL_ETAPA)
    if not is_apoio and any(_contem(etapa, e) for e in ETAPAS_EF_6_9):
        if escolaridade != "Educação superior":
            erros.append(("escolaridade_sup", "Professor de Anos Finais Sem Ensino Superior"))

    return erros


def _chave_profissional(row: pd.Series) -> tuple[str, str]:
    codigo = str(row.get("Código do Inep", "")).strip()
    identificacao = str(row.get(COL_IDENTIFICACAO, "")).strip()
    if identificacao:
        return (codigo, identificacao)
    return (codigo, str(row.get("Nome", "")).strip())


def validate_profissionais(
    df: pd.DataFrame,
    escolas: list[dict],
) -> list[dict]:
    agrupado: dict[tuple[str, str], dict] = {}

    for _, row in df.iterrows():
        erros = _validar_linha(row)
        if not erros:
            continue
        chave = _chave_profissional(row)
        grupo = agrupado.setdefault(chave, {
            "codigo_inep": row.get("Código do Inep", ""),
            "nome_unidade": row.get("Nome da Unidade", ""),
            "nome_profissional": row.get("Nome", ""),
            "identificacao_unica": row.get(COL_IDENTIFICACAO, ""),
            "_erros": [],
        })
        for regra_id, mensagem in erros:
            if regra_id not in {r for r, _ in grupo["_erros"]}:
                grupo["_erros"].append((regra_id, mensagem))

    resultados: list[dict] = []
    for grupo in agrupado.values():
        itens = grupo.pop("_erros")
        erros = [mensagem for _, mensagem in itens]
        resultados.append({
            "codigo_inep": grupo["codigo_inep"],
            "nome_unidade": grupo["nome_unidade"],
            "nome_profissional": grupo["nome_profissional"],
            "identificacao_unica": grupo["identificacao_unica"],
            "tipo_validacao": "profissionais",
            "status": "inconsistente",
            "erros": erros,
            "detalhes": "; ".join(erros),
        })
    return resultados
