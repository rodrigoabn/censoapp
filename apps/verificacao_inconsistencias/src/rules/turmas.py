from __future__ import annotations

import pandas as pd

TIPO_CURRICULAR = "Curricular (etapa de ensino)"

ORGANIZACAO_EJA = "Educação de Jovens e Adultos (ensino fundamental, ensino médio e integrada)"
ORGANIZACAO_SEMESTRAL = "Períodos semestrais"

ETAPA_EJA_ANOS_INICIAIS = "EJA - Ensino fundamental - anos iniciais (1º segmento)"
ETAPA_EJA_ANOS_FINAIS_1 = "EJA - Ensino fundamental - anos finais (1º segmento)"
ETAPA_EJA_ANOS_FINAIS_2 = "EJA - Ensino fundamental - anos finais (2º segmento)"
ETAPA_MULTIETAPA = "Educação infantil e ensino fundamental – multietapa"

ETAPA_EF_9 = [
    "Ensino fundamental de 9 anos - 1º Ano",
    "Ensino fundamental de 9 anos - 2º Ano",
    "Ensino fundamental de 9 anos - 3º Ano",
    "Ensino fundamental de 9 anos - 4º Ano",
    "Ensino fundamental de 9 anos - 5º Ano",
    "Ensino fundamental de 9 anos - 6º Ano",
    "Ensino fundamental de 9 anos - 7º Ano",
    "Ensino fundamental de 9 anos - 8º Ano",
    "Ensino fundamental de 9 anos - 9º Ano",
]

ETAPAS_EF_1_5 = ETAPA_EF_9[:5]

ETAPAS_EF_6_9 = ETAPA_EF_9[5:]

ETAPA_MULTI = "Ensino Fundamental de 9 anos - multi"
ETAPA_CORRECAO_FLUXO = "Ensino Fundamental de 9 anos - correção de fluxo"
ETAPA_CRECHE = "Educação infantil - creche (0 a 3 anos)"
ETAPA_PRE_ESCOLA = "Educação infantil - pré-escola (4 e 5 anos)"
ETAPA_AGREGADA_EDUCACAO_INFANTIL = "Educação Infantil"

_ETAPA_EF_9_POR_ANO = {str(i): e for i, e in enumerate(ETAPA_EF_9, start=1)}

PERIODO_ETAPA_ESPERADA: dict[str, tuple[str, ...]] = {
    **{f"{i}A": (_ETAPA_EF_9_POR_ANO[str(i)],) for i in range(1, 10)},
    **{f"{i}F": (ETAPA_EJA_ANOS_INICIAIS,) for i in range(1, 6)},
    **{f"{i}F": (ETAPA_EJA_ANOS_FINAIS_2,) for i in range(6, 10)},
    "G1": (ETAPA_CRECHE,),
    "G2": (ETAPA_CRECHE,),
    "G3": (ETAPA_CRECHE,),
    "P1": (ETAPA_PRE_ESCOLA,),
    "P2": (ETAPA_PRE_ESCOLA,),
    "MF": (ETAPA_EJA_ANOS_INICIAIS, ETAPA_EJA_ANOS_FINAIS_2),
    "NI": (ETAPA_CORRECAO_FLUXO,),
    "NF": (ETAPA_CORRECAO_FLUXO,),
    "MA": (ETAPA_MULTI,),
}

MSG_SIGLA_ETAPA = "Divergência entre Sigla e Etapa"
MSG_CARGA_M_T = "Carga Horária menor que 20h ou maior do que 35h."
MSG_CARGA_I = "Integral não pode ser inferior a 35h"

_AREA_MULTIETAPA_EF_1_5 = {
    "Matemática",
    "Ciências",
    "Língua /Literatura Portuguesa",
    "Arte (Educação Artística, Teatro, Dança, Música, Artes Plásticas e outras)",
    "Educação Física",
    "História",
    "Geografia",
    "Informática/Computação",
    "Ensino religioso",
    "Outras Áreas do Conhecimento",
}

_AREA_EF_6_9 = _AREA_MULTIETAPA_EF_1_5 | {"Língua /Literatura estrangeira - Inglês"}

_AREA_EJA_FINAIS_2 = {
    "Matemática",
    "Ciências",
    "Língua /Literatura Portuguesa",
    "Língua /Literatura estrangeira - Inglês",
    "Arte (Educação Artística, Teatro, Dança, Música, Artes Plásticas e outras)",
    "Educação Física",
    "História",
    "Geografia",
    "Ensino religioso",
    "Outras Áreas do Conhecimento",
}

_AREA_EJA_FINAIS_1 = {
    "Matemática",
    "Ciências",
    "Língua /Literatura Portuguesa",
    "Arte (Educação Artística, Teatro, Dança, Música, Artes Plásticas e outras)",
    "Educação Física",
    "História",
    "Geografia",
    "Outras Áreas do Conhecimento",
}

_COLS_ESPECIAIS = (
    "Turma de Educação Especial (classe especial)",
    "Turma de Educação Bilingue de Surdos (classe bilingue de surdos)",
    "Formação por Alternância (proposta pedagógica de formação por alternância tempo - escola e tempo - comunidade)",
)

_H15 = 15 * 3600
_H20 = 20 * 3600
_H35 = 35 * 3600


def _to_seconds(val) -> float | None:
    if val is None:
        return None
    s = str(val).strip().replace(",", ":")
    if not s or s.lower() in ("--", "-", "nan", "none"):
        return None
    parts = [p for p in s.split(":") if p.strip()]
    if not parts:
        return None
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return None
    if len(nums) == 1:
        return nums[0] * 3600
    if len(nums) == 2:
        return nums[0] * 3600 + nums[1] * 60
    return nums[0] * 3600 + nums[1] * 60 + (nums[2] if len(nums) > 2 else 0)


def _contem(texto: str, busca: str) -> bool:
    return busca.lower() in (texto or "").lower()


def _periodo_turma(nome) -> str:
    nome = str(nome or "")
    return nome[:2]


def _verifica_integral(nome) -> str:
    nome = str(nome or "")
    return nome[2:3]


def _parse_areas(val) -> set[str]:
    if val is None:
        return set()
    return {p.strip() for p in str(val).split("|") if p.strip()}


def _area_diff(esperado: set[str], atual: set[str]) -> str:
    exp_low = {e.lower(): e for e in esperado}
    atu_low = {a.lower(): a for a in atual}
    faltando = sorted(exp_low[k] for k in exp_low if k not in atu_low)
    extras = sorted(atu_low[k] for k in atu_low if k not in exp_low)
    msgs = [f"'{c}' não informado." for c in faltando]
    msgs += [f"'{c}' não deve ser informado." for c in extras]
    return "; ".join(msgs)


def _area_esperada_para(etapa: str) -> set[str] | None:
    if _contem(etapa, ETAPA_MULTIETAPA):
        return _AREA_MULTIETAPA_EF_1_5
    for e in ETAPAS_EF_1_5:
        if _contem(etapa, e):
            return _AREA_MULTIETAPA_EF_1_5
    for e in ETAPAS_EF_6_9:
        if _contem(etapa, e):
            return _AREA_EF_6_9
    if _contem(etapa, ETAPA_EJA_ANOS_FINAIS_2):
        return _AREA_EJA_FINAIS_2
    if _contem(etapa, ETAPA_EJA_ANOS_FINAIS_1):
        return _AREA_EJA_FINAIS_1
    return None


def _validar_linha(row: pd.Series) -> list[str]:
    erros: list[str] = []

    def get(col: str) -> str:
        v = row.get(col)
        return "" if v is None else str(v).strip()

    tipo_turma = get("Tipo de turma")
    if tipo_turma != TIPO_CURRICULAR:
        erros.append("Tipo de turma deve ser 'Curricular (etapa de ensino)'.")

    nome_raw = str(row.get("Nome da turma") or "")
    nome = get("Nome da turma")
    if not nome:
        erros.append("Nome da turma não informado.")
    else:
        if len(nome) != 5:
            erros.append("Nome da turma deve ter exatamente 5 caracteres.")
        if any(ch.isspace() for ch in nome_raw):
            erros.append("Nome da turma não pode conter espaços.")
        if len(nome) >= 3 and nome[2] not in "MTNI":
            erros.append("O 3º caractere do nome da turma deve ser 'M', 'T', 'N' ou 'I'.")

    etapa_agregada = get("Etapa Agregada")
    if _contem(etapa_agregada, ORGANIZACAO_EJA):
        formas = get("Formas de organização da turma")
        if formas != ORGANIZACAO_SEMESTRAL:
            erros.append(
                "Quando 'Etapa Agregada' for EJA, 'Formas de organização da turma' deve ser 'Períodos semestrais'."
            )

    etapa_ensino = get("Etapa de ensino")
    horas = _to_seconds(get("Carga horária semanal (hh:mm)"))

    if horas is not None:
        if _contem(etapa_ensino, ETAPA_EJA_ANOS_INICIAIS):
            if horas < _H15:
                erros.append("Carga horária semanal não pode ser menor que 15:00:00.")
            if horas > _H20:
                erros.append("Carga horária semanal não pode ser maior que 20:00:00.")
        eh_ef_ou_infantil = not _contem(etapa_agregada, ORGANIZACAO_EJA) and (
            _contem(etapa_agregada, "Ensino Fundamental") or _contem(etapa_agregada, "Educação Infantil")
        )
        if eh_ef_ou_infantil:
            if horas < _H20:
                erros.append(
                    "Para 'Etapa Agregada' de Ensino Fundamental ou Educação Infantil, "
                    "a carga horária semanal não pode ser menor que 20:00:00."
                )
        if len(nome) >= 3 and nome[2] == "I" and horas < _H35:
            erros.append(
                "Para turmas com 3º caractere 'I' no nome, "
                "a carga horária semanal deve ser maior ou igual a 35:00:00."
            )

    dias = get("Dias da semana e horário de funcionamento").lower()
    if "sábado" in dias or "domingo" in dias:
        erros.append("'Dias da semana e horário de funcionamento' não pode conter 'Sábado' ou 'Domingo'.")

    area_esperada = _area_esperada_para(etapa_ensino)
    if area_esperada is not None:
        areas_atual = _parse_areas(get("Áreas do conhecimento/componentes curriculares"))
        if {a.lower() for a in areas_atual} != {a.lower() for a in area_esperada}:
            diff = _area_diff(area_esperada, areas_atual)
            if diff:
                erros.append(diff)

    for col in _COLS_ESPECIAIS:
        if get(col) != "Não":
            erros.append(f"'{col}' deve ser 'Não'.")

    return erros


def _validar_escolarizacao(row: pd.Series) -> list[str]:
    erros: list[str] = []

    def get(col: str) -> str:
        v = row.get(col)
        return "" if v is None else str(v).strip()

    periodo = _periodo_turma(get("Nome da turma"))
    verifica = _verifica_integral(get("Nome da turma"))
    etapa = get("Etapa de ensino")

    esperadas = PERIODO_ETAPA_ESPERADA.get(periodo)
    if esperadas is not None and not any(_contem(etapa, e) for e in esperadas):
        erros.append(MSG_SIGLA_ETAPA)

    if _contem(etapa, "multietapa"):
        if periodo != "IF":
            erros.append(MSG_SIGLA_ETAPA)
    elif _contem(etapa, ETAPA_MULTI):
        if periodo != "MA":
            erros.append(MSG_SIGLA_ETAPA)
    elif _contem(etapa, ETAPA_CORRECAO_FLUXO):
        if periodo not in ("NI", "NF"):
            erros.append(MSG_SIGLA_ETAPA)

    if periodo == "MI" and get("Etapa Agregada") != ETAPA_AGREGADA_EDUCACAO_INFANTIL:
        erros.append(MSG_SIGLA_ETAPA)

    horas = _to_seconds(get("Carga horária semanal (hh:mm)"))
    if horas is not None:
        if verifica in ("M", "T") and not (_H20 <= horas <= _H35):
            erros.append(MSG_CARGA_M_T)
        elif verifica == "I" and horas < _H35:
            erros.append(MSG_CARGA_I)

    return list(dict.fromkeys(erros))


def validate_turmas_escolarizacao(df_escolarizacao: pd.DataFrame) -> list[dict]:
    resultados: list[dict] = []

    for _, row in df_escolarizacao.iterrows():
        erros = _validar_escolarizacao(row)
        if erros:
            resultados.append({
                "codigo_inep": row.get("Código do Inep", ""),
                "nome_unidade": row.get("Nome da Unidade", ""),
                "nome_turma": row.get("Nome da turma", ""),
                "etapa_ensino": row.get("Etapa de ensino", ""),
                "carga_horaria": row.get("Carga horária semanal (hh:mm)", ""),
                "periodo_turma": _periodo_turma(row.get("Nome da turma", "")),
                "verifica_integral": _verifica_integral(row.get("Nome da turma", "")),
                "tipo_validacao": "turmas_escolarizacao",
                "status": "inconsistente",
                "erros": erros,
                "detalhes": "; ".join(erros),
            })
    return resultados


def validate_turmas(
    df_aee: pd.DataFrame,
    df_atv: pd.DataFrame,
    df_curricular: pd.DataFrame,
    df_escolarizacao: pd.DataFrame | None = None,
) -> list[dict]:
    resultados: list[dict] = []

    for _, row in df_curricular.iterrows():
        erros = _validar_linha(row)
        if erros:
            resultados.append({
                "codigo_inep": row.get("Código do Inep", ""),
                "nome_unidade": row.get("Nome da Unidade", ""),
                "nome_turma": row.get("Nome da turma", ""),
                "etapa_ensino": row.get("Etapa de ensino", ""),
                "carga_horaria": row.get("Carga horária semanal (hh:mm)", ""),
                "periodo_turma": _periodo_turma(row.get("Nome da turma", "")),
                "verifica_integral": _verifica_integral(row.get("Nome da turma", "")),
                "tipo_validacao": "turmas_curricular",
                "status": "inconsistente",
                "erros": erros,
                "detalhes": "; ".join(erros),
            })
    if df_escolarizacao is not None:
        resultados.extend(validate_turmas_escolarizacao(df_escolarizacao))
    return resultados
