from __future__ import annotations

import re
import unicodedata
from collections import Counter

import pandas as pd

COL_CPF = "CPF"
COL_IDENTIFICACAO = "Identificação única"
COL_NOME = "Nome"
COL_MATRICULA = "Código da Matrícula"
COL_TURMA = "Código da turma"
COL_NOME_TURMA = "Nome da turma"
COL_NASCIMENTO = "Data de nascimento"
COL_LOCALIZACAO = "Localização/Zona de residência"
COL_TRANSPORTE = "Transporte escolar (Sim/Não)"
COL_PODER_PUBLICO = "Poder Público responsável"
COL_ETAPA_ENSINO = "Etapa de ensino"


def _cpf_digitos(val) -> str:
    if val is None:
        return ""
    digitos = re.sub(r"\D", "", str(val))
    if len(digitos) == 11:
        return digitos
    return ""


def _normalizar(val) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    if s.lower() in ("--", "-", "nan", "none", ""):
        return ""
    return s


def _calcular_idade(val, ano: int | None) -> int | None:
    if not ano:
        return None
    try:
        nasc = pd.to_datetime(val, dayfirst=True, errors="coerce")
    except Exception:
        return None
    if nasc is None or pd.isna(nasc):
        return None
    ref = pd.Timestamp(ano, 3, 31)
    idade = ref.year - nasc.year
    if (ref.month, ref.day) < (nasc.month, nasc.day):
        idade -= 1
    return idade


def _periodo(val) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    if len(s) < 2:
        return ""
    return s[:2].upper()


def _norm_etapa(val) -> str:
    if val is None:
        return ""
    s = str(val).strip().lower()
    s = s.replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s)


_ETAPA_CRECHE = "educação infantil - creche (0 a 3 anos)"
_ETAPA_PRE = "educação infantil - pré-escola (4 e 5 anos)"

_ETAPAS_EJA = {
    "eja - ensino fundamental - anos iniciais (1º segmento)",
    "eja - ensino fundamental - anos finais (2º segmento)",
}

_ETAPAS_EF_9 = {
    "ensino fundamental de 9 anos - correção de fluxo",
    "ensino fundamental de 9 anos - multi",
    "ensino fundamental de 9 anos - 1º ano",
    "ensino fundamental de 9 anos - 2º ano",
    "ensino fundamental de 9 anos - 3º ano",
    "ensino fundamental de 9 anos - 4º ano",
    "ensino fundamental de 9 anos - 5º ano",
    "ensino fundamental de 9 anos - 6º ano",
    "ensino fundamental de 9 anos - 7º ano",
    "ensino fundamental de 9 anos - 8º ano",
    "ensino fundamental de 9 anos - 9º ano",
}

MSG_IDADE = "Idade incompatível com turma"


def _regras_periodo(periodo: str, idade: int | None) -> bool:
    if idade is None:
        return False
    if periodo == "G1":
        return idade not in (0, 1)
    if periodo == "G2":
        return idade != 2
    if periodo == "G3":
        return idade != 3
    if periodo == "P1":
        return idade != 4
    if periodo == "P2":
        return idade != 5
    if periodo == "MI":
        return idade > 5
    return False


def validate_aluno(
    df: pd.DataFrame,
    escolas: list[dict] | None = None,
    ano_letivo: int | None = None,
) -> list[dict]:
    resultados: list[dict] = []

    for _, row in df.iterrows():
        erros: list[str] = []

        if not _normalizar(row.get(COL_LOCALIZACAO)):
            erros.append("Sem Zona Residencial informada")

        if _normalizar(row.get(COL_TRANSPORTE)) == "Sim":
            if _normalizar(row.get(COL_PODER_PUBLICO)) != "Municipal":
                erros.append("Transporte Escolar não informado como Municipal")

        idade = _calcular_idade(row.get(COL_NASCIMENTO), ano_letivo)
        periodo = _periodo(row.get(COL_NOME_TURMA))
        etapa = _norm_etapa(row.get(COL_ETAPA_ENSINO))

        if _regras_periodo(periodo, idade):
            erros.append(MSG_IDADE)

        if idade is not None:
            if etapa == _ETAPA_CRECHE and idade > 3:
                erros.append(MSG_IDADE)
            elif etapa == _ETAPA_PRE and idade not in (4, 5):
                erros.append(MSG_IDADE)
            elif etapa in _ETAPAS_EJA and idade < 15:
                erros.append(MSG_IDADE)
            elif etapa in _ETAPAS_EF_9 and idade < 6:
                erros.append(MSG_IDADE)

        if erros:
            erros = list(dict.fromkeys(erros))
            resultados.append({
                "codigo_inep": row.get("Código do Inep", ""),
                "nome_unidade": row.get("Nome da Unidade", ""),
                "nome": row.get(COL_NOME, ""),
                "identificacao_unica": row.get(COL_IDENTIFICACAO, ""),
                "data_nascimento": row.get(COL_NASCIMENTO, ""),
                "nome_turma": row.get(COL_NOME_TURMA, ""),
                "etapa_ensino": row.get(COL_ETAPA_ENSINO, ""),
                "idade": idade,
                "periodo": periodo,
                "tipo_validacao": "aluno_curricular",
                "status": "inconsistente",
                "erros": erros,
                "detalhes": "; ".join(erros),
            })
    return resultados


def find_matriculas_duplicadas(df: pd.DataFrame) -> list[dict]:
    linhas = list(df.iterrows())
    cpf_contagem: Counter = Counter()
    id_contagem: Counter = Counter()

    cpfs: list[str] = []
    ids: list[str] = []
    for _, row in linhas:
        cpf = _cpf_digitos(row.get(COL_CPF))
        idu = _normalizar(row.get(COL_IDENTIFICACAO))
        cpfs.append(cpf)
        ids.append(idu)
        if cpf:
            cpf_contagem[cpf] += 1
        if idu:
            id_contagem[idu] += 1

    duplicadas: list[dict] = []
    for (_, row), cpf, idu in zip(linhas, cpfs, ids):
        motivo: list[str] = []
        if cpf and cpf_contagem[cpf] > 1:
            motivo.append("CPF duplicado")
        if idu and id_contagem[idu] > 1:
            motivo.append("Identificação única duplicada")
        if not motivo:
            continue
        duplicadas.append({
            "codigo_inep": row.get("Código do Inep", ""),
            "nome_unidade": row.get("Nome da Unidade", ""),
            "nome": row.get(COL_NOME, ""),
            "identificacao_unica": row.get(COL_IDENTIFICACAO, ""),
            "cpf": row.get(COL_CPF, ""),
            "motivo": " e ".join(motivo),
            "codigo_matricula": row.get(COL_MATRICULA, ""),
            "codigo_turma": row.get(COL_TURMA, ""),
            "nome_turma": row.get(COL_NOME_TURMA, ""),
        })

    duplicadas.sort(key=lambda r: (str(r["identificacao_unica"]), str(r["cpf"]),
                                   str(r["codigo_inep"]), str(r["codigo_matricula"])))
    return duplicadas


def extrair_alunos_sem_cpf(df: pd.DataFrame) -> list[dict]:
    registros: list[dict] = []
    for _, row in df.iterrows():
        if _normalizar(row.get(COL_CPF)):
            continue
        registros.append({
            "codigo_inep": row.get("Código do Inep", ""),
            "nome_unidade": row.get("Nome da Unidade", ""),
            "identificacao_unica": row.get(COL_IDENTIFICACAO, ""),
            "nome": row.get(COL_NOME, ""),
            "cpf": row.get(COL_CPF, ""),
        })

    registros.sort(key=lambda r: (str(r["codigo_inep"]), str(r["nome"])))
    return registros


COL_COR_RACA = "Cor/Raça"
COL_LOCALIZACAO_DIFERENCIADA = "Localização diferenciada de residência"

#: Parâmetros com ordem fixa no quantitativo; os demais valores da coluna
#: entram em ordem alfabética e "Sem informação" sempre por último.
_ORDEM_PARAMETROS = ("Sim", "Não")

#: Balde usado quando a coluna está vazia, "--", "-" ou NaN.
PARAMETRO_SEM_INFORMACAO = "Sem informação"


def _parametro_localizacao_diferenciada(valor) -> str:
    """Valor canônico do parâmetro de localização diferenciada de residência."""
    if valor is None:
        return PARAMETRO_SEM_INFORMACAO
    texto = str(valor).strip()
    if not texto or texto.lower() in ("--", "-", "nan", "none"):
        return PARAMETRO_SEM_INFORMACAO
    return texto


def _chave_alfabetica(texto: str) -> str:
    """Chave de ordenação alfabética que ignora acentos e caixa.

    "Área rural" ordena antes de "Zona urbana" — a comparação por ponto de
    código colocaria "Z" antes de "Á".
    """
    sem_acento = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).casefold()


def _ordem_parametros(valores: set[str]) -> list[str]:
    """Ordena os parâmetros: conhecidos, demais em ordem alfabética (sem
    diferenciar acentos nem caixa) e "Sem informação" por último."""
    conhecidos = [v for v in _ORDEM_PARAMETROS if v in valores]
    outros = sorted(
        (
            v for v in valores
            if v not in _ORDEM_PARAMETROS and v != PARAMETRO_SEM_INFORMACAO
        ),
        key=_chave_alfabetica,
    )
    fim = [PARAMETRO_SEM_INFORMACAO] if PARAMETRO_SEM_INFORMACAO in valores else []
    return conhecidos + outros + fim


def levantamento_matriculas_localizacao_diferenciada(df: pd.DataFrame) -> list[dict]:
    """Conta matrículas por unidade escolar pelos parâmetros da coluna
    "Localização diferenciada de residência".

    Uma linha por escola, com a contagem de matrículas em cada parâmetro
    ("Sim", "Não", demais valores da coluna e "Sem informação") e o total.
    As escolas entram na ordem de primeira aparição no arquivo.
    """
    agregados: dict[tuple[str, str], dict[str, int]] = {}
    parametros: set[str] = set()

    for _, row in df.iterrows():
        codigo = str(row.get("Código do Inep", "")).strip()
        nome = str(row.get("Nome da Unidade", "")).strip()
        chave = (codigo, nome)
        if chave not in agregados:
            agregados[chave] = {}
        parametro = _parametro_localizacao_diferenciada(
            row.get(COL_LOCALIZACAO_DIFERENCIADA)
        )
        parametros.add(parametro)
        agregados[chave][parametro] = agregados[chave].get(parametro, 0) + 1

    ordem = _ordem_parametros(parametros)
    registros: list[dict] = []
    for (codigo, nome), contagens in agregados.items():
        registros.append({
            "codigo_inep": codigo,
            "nome_unidade": nome,
            "total": sum(contagens.values()),
            "contagens": {p: contagens.get(p, 0) for p in ordem},
        })
    return registros


def _bucket_cor_raca(val) -> str | None:
    if val is None:
        return "sem_informacao"
    s = str(val).strip().lower()
    if not s or s in ("--", "-", "nan", "none"):
        return "sem_informacao"
    if "branca" in s:
        return "branca"
    if "preta" in s:
        return "preta"
    if "parda" in s:
        return "parda"
    if "amarela" in s:
        return "amarela"
    if "indígena" in s or "indigena" in s:
        return "indigena"
    if "declar" in s:
        return "nao_declarado"
    return "sem_informacao"


def levantamento_cor_raca(df: pd.DataFrame) -> list[dict]:
    registros: dict[tuple[str, str], dict] = {}

    for _, row in df.iterrows():
        codigo = str(row.get("Código do Inep", "")).strip()
        nome = str(row.get("Nome da Unidade", "")).strip()
        chave = (codigo, nome)
        reg = registros.setdefault(chave, {
            "codigo_inep": codigo,
            "nome_unidade": nome,
            "preta": 0,
            "parda": 0,
            "branca": 0,
            "amarela": 0,
            "indigena": 0,
            "nao_declarado": 0,
            "sem_informacao": 0,
        })
        bucket = _bucket_cor_raca(row.get(COL_COR_RACA))
        reg[bucket] += 1

    return list(registros.values())
