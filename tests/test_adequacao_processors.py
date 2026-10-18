"""Testes golden dos processadores de adequação (turmas, alunos, profissionais).

Os três apps repetem o mesmo pipeline em `processor.py`; os helpers de
formatação `_remove_aspas`, `_completar_cpf` e `_formatar_data` são duplicados
byte a byte em alunos e profissionais — por isso os mesmos casos rodam contra
**as duas cópias**.

Etapas do pipeline pinadas:

1. descarte do preâmbulo (14 linhas em turmas; 15 em alunos/profissionais —
   somente quando o frame tem mais linhas que isso);
2. remoção da 3ª e 5ª coluna (turmas) / 3ª e 4ª (alunos/profissionais);
3. remoção do rodapé: se existir coluna `Ordem`, corta após a última linha com
   número puro (`^\\d+(\\.\\d+)?$`); senão descarta as últimas 4/5 linhas;
4. renomeação posicional para as colunas-alvo; com colunas a mais, as
   excedentes são descartadas; com colunas a menos, o `reindex` casa por
   rótulo — só colunas que já se chamavam como o alvo sobrevivem, o resto vira
   NaN (quirk congelado — corrigir é decisão de produto);
5. formatação de Identificação única / CPF / Data de nascimento — com "N"
   maiúsculo **só** em profissionais.

Observações pinadas:

- A docstring de `adeguar_alunos` diz "25 colunas", mas a lista `novas_colunas`
  tem **26**; os snapshots abaixo seguem o código.
- CPF com 11+ dígitos volta como veio (máscara preservada); abaixo disso vira
  dígitos com zeros à esquerda.
- As listas de colunas-alvo são retratos (snapshot) das literais internas dos
  processadores — se a produção mudar cabeçalho/ordem, estes testes falham.
"""

from __future__ import annotations

import pandas as pd
import pytest

from apps.adequacao_alunos.src import processor as alunos
from apps.adequacao_profissionais.src import processor as profissionais
from apps.adequacao_turmas.src import processor as turmas

TURMAS_COLUNAS = [
    "Ordem",
    "Código da turma",
    "Nome da turma",
    "Tipo de mediação didático-pedagógica",
    "Tipo de turma",
    "Etapa Agregada",
    "Etapa de ensino",
    "Carga horária total do curso",
    "Carga horária semanal (hh:mm)",
    "Formas de organização da turma",
    "Local de funcionamento diferenciado da turma",
    "Dias da semana e horário de funcionamento",
    "Turma de Educação Especial (classe especial)",
    "Turma de Educação Bilingue de Surdos (classe bilingue de surdos)",
    "Formação por Alternância (proposta pedagógica de formação por alternância tempo - escola e tempo - comunidade)",
    "Áreas do conhecimento/componentes curriculares",
    "Organização curricular da turma",
    "Área(s) do itinerário formativo",
    "Tipo de curso do itinerário de formação técnica e profissional",
    "Código e nome do curso técnico",
    "Atividade (s) complementar (es)",
    "Quantidade de Alunos (as)",
    "Quantidade de Profissionais escolares",
]

ALUNOS_COLUNAS = [
    "Ordem",
    "Identificação única",
    "Nome",
    "Data de nascimento",
    "CPF",
    "Nacionalidade",
    "Município-UF de nascimento",
    "Cor/Raça",
    "Povo indígena",
    "Sexo",
    "Tipo(s) de deficiência(s), transtorno(s) do espectro autista e altas habilidades ou superdotação",
    "Tipo(s) de transtorno(s) que impacta(m) o desenvolvimento da aprendizagem",
    "Recursos para o uso do(a) aluno(a) em sala de aula para a participação em avaliações do Inep (Saeb)",
    "Localização/Zona de residência",
    "Localização diferenciada de residência",
    "Código da Matrícula",
    "Código da turma",
    "Nome da turma",
    "Etapa de ensino",
    "Tipo de atendimento educacional especializado (AEE)",
    "Recebe atendimento educacional em regime hospitalar ou domiciliar",
    "Transporte escolar (Sim/Não)",
    "Poder Público responsável",
    "Tipo de veículo utilizado no transporte escolar",
    "Etapa de vínculo do(a) aluno(a) (Para turmas do tipo multi)",
    "Carga horária integralizada pelo(a) aluno(a) no curso técnico ou de qualificação profissional",
]

PROFISSIONAIS_COLUNAS = [
    "Ordem",
    "Identificação única",
    "Nome",
    "Data de Nascimento",
    "CPF",
    "Nacionalidade",
    "Cor/Raça",
    "Povo Indígena",
    "Sexo",
    "Tipo(s) de deficiência(s), transtorno(s) do espectro autista e altas habilidades ou superdotação",
    "Localização/Zona de residência",
    "Localização diferenciada de residência",
    "Maior nível de escolaridade concluído",
    "Tipo de ensino médio cursado",
    "Pós-Graduação concluída",
    "Formação/Complementação Pedagógica",
    "Outros cursos específicos (Formação continuada com no mínimo 80 horas)",
    "Código da turma",
    "Nome da Turma",
    "Etapa de ensino",
    "Situação Funcional / Regime de contratação / Tipo de vínculo",
    "Função que exerce na turma",
    "Áreas do conhecimento/componentes curriculares que leciona (FGB)",
    "Área(s) do Itinerário formativo que leciona (IFA)",
    "Tipo do curso do itinerário de formação técnica e profissional que leciona",
]

# ─────────────────────── helpers duplicados ──────────────────

_MODULOS_FORMATO = [
    pytest.param(alunos, id="alunos"),
    pytest.param(profissionais, id="profissionais"),
]

_REMOVE_ASPAS = [
    pytest.param('="110094711207"', "110094711207", id="prefixo-igual-aspas"),
    pytest.param('"123"', "123", id="apenas-aspas"),
    pytest.param('="123', "123", id="sem-fechamento"),
    pytest.param("=123", "=123", id="igual-sem-aspas-mantido"),
    pytest.param("texto", "texto", id="texto-normal"),
    pytest.param("", "", id="vazio"),
    pytest.param(None, "None", id="nao-str-vira-str"),
    pytest.param(123, "123", id="int-vira-str"),
]

_CPF = [
    pytest.param("123", "00000000123", id="completa-zeros"),
    pytest.param("123.456.789", "00123456789", id="mascara-parcial-vira-digitos"),
    pytest.param("123.456.789-09", "123.456.789-09", id="onze-digitos-preserva-mascara"),
    pytest.param("1100947112070", "1100947112070", id="mais-de-onze-sem-corte"),
    pytest.param("--", "--", id="placeholder-traco-duplo"),
    pytest.param("-", "-", id="placeholder-traco"),
    pytest.param("", "", id="vazio"),
    pytest.param("nan", "nan", id="nan"),
    pytest.param("NAN", "NAN", id="nan-caixa-alta-preserva-original"),
    pytest.param("  123  ", "00000000123", id="espacos"),
    pytest.param("abc", "abc", id="sem-digitos"),
]

_DATA = [
    pytest.param("5/3/2010", "05/03/2010", id="d-m-aaaa"),
    pytest.param("05/03/2010", "05/03/2010", id="dd-mm-aaaa-ja-ok"),
    pytest.param("2010-03-05", "05/03/2010", id="aaaa-mm-dd"),
    pytest.param("2010-3-5", "05/03/2010", id="aaaa-m-d"),
    pytest.param("5-3-2010", "05/03/2010", id="d-m-aaaa-com-hifen"),
    pytest.param("05-03-2010", "05/03/2010", id="dd-mm-aaaa-com-hifen"),
    pytest.param("31/12/2010", "31/12/2010", id="fim-de-ano"),
    pytest.param("", "", id="vazio"),
    pytest.param("nan", "nan", id="nan"),
    pytest.param("NaT", "NaT", id="nat"),
    pytest.param(None, None, id="none"),
    pytest.param("1/1/1", "1/1/1", id="formato-desconhecido"),
]


@pytest.mark.parametrize("modulo", _MODULOS_FORMATO)
@pytest.mark.parametrize("entrada,esperado", _REMOVE_ASPAS)
def test_remove_aspas(modulo, entrada, esperado):
    assert modulo._remove_aspas(entrada) == esperado


@pytest.mark.parametrize("modulo", _MODULOS_FORMATO)
@pytest.mark.parametrize("entrada,esperado", _CPF)
def test_completar_cpf(modulo, entrada, esperado):
    assert modulo._completar_cpf(entrada) == esperado


@pytest.mark.parametrize("modulo", _MODULOS_FORMATO)
@pytest.mark.parametrize("entrada,esperado", _DATA)
def test_formatar_data(modulo, entrada, esperado):
    assert modulo._formatar_data(entrada) == esperado


# ────────────────────────── construtores ─────────────────────


def _turmas_brutas(n_dados: int) -> pd.DataFrame:
    colunas = ["Ordem"] + [f"c{i}" for i in range(1, 25)]  # 25 colunas
    linhas = [[f"x{i}"] + [""] * 24 for i in range(14)]
    for i in range(1, n_dados + 1):
        linhas.append([str(i)] + [f"v{i}-{j}" for j in range(1, 25)])
    linhas.append(["Fonte: Educacenso"] + [""] * 24)
    linhas.append(["Nota"] + [""] * 24)
    linhas.append(["1 - Os dados"] + [""] * 24)
    linhas.append(["Emitido"] + [""] * 24)
    return pd.DataFrame(linhas, columns=colunas)


def _alunos_brutos(n_dados: int) -> pd.DataFrame:
    colunas = ["Ordem"] + [f"c{i}" for i in range(1, 28)]  # 28 colunas
    linhas = [[f"x{i}"] + [""] * 27 for i in range(15)]
    for i in range(1, n_dados + 1):
        linhas.append([str(i)] + [f"v{i}-{j}" for j in range(1, 28)])
    linhas.append(["Fonte: Educacenso"] + [""] * 27)
    linhas.append(["Nota"] + [""] * 27)
    linhas.append(["1 - Os dados"] + [""] * 27)
    linhas.append(["2 - "] + [""] * 27)
    linhas.append(["Emitido"] + [""] * 27)
    return pd.DataFrame(linhas, columns=colunas)


def _profissionais_brutos(n_dados: int) -> pd.DataFrame:
    colunas = ["Ordem"] + [f"c{i}" for i in range(1, 27)]  # 27 colunas
    linhas = [[f"x{i}"] + [""] * 26 for i in range(15)]
    for i in range(1, n_dados + 1):
        linhas.append([str(i)] + [f"v{i}-{j}" for j in range(1, 27)])
    linhas.append(["Fonte: Educacenso"] + [""] * 26)
    linhas.append(["Nota"] + [""] * 26)
    linhas.append(["1 - Os dados"] + [""] * 26)
    linhas.append(["2 - "] + [""] * 26)
    linhas.append(["Emitido"] + [""] * 26)
    return pd.DataFrame(linhas, columns=colunas)


# ────────────────────────── turmas ───────────────────────────


def test_adequar_turmas_fluxo_completo():
    resultado = turmas.adequar_turmas({
        "a.csv": _turmas_brutas(4),
        "b.csv": _turmas_brutas(1),
    })
    assert list(resultado) == ["a.csv", "b.csv"]
    df_a = resultado["a.csv"]
    assert list(df_a.columns) == TURMAS_COLUNAS
    assert len(df_a) == 4
    assert df_a["Ordem"].tolist() == ["1", "2", "3", "4"]
    assert df_a["Código da turma"].tolist() == ["v1-1", "v2-1", "v3-1", "v4-1"]
    assert df_a["Nome da turma"].tolist() == ["v1-3", "v2-3", "v3-3", "v4-3"]
    assert df_a["Tipo de turma"].tolist() == ["v1-6", "v2-6", "v3-6", "v4-6"]
    assert df_a["Quantidade de Profissionais escolares"].tolist() == [
        "v1-24", "v2-24", "v3-24", "v4-24",
    ]
    assert len(resultado["b.csv"]) == 1


def test_adequar_turmas_descarta_coluna_excedente():
    colunas = ["Ordem"] + [f"c{i}" for i in range(1, 26)]  # 26 colunas
    linhas = [
        ["1"] + [f"v{j}" for j in range(1, 26)],
        ["2"] + [f"w{j}" for j in range(1, 26)],
    ]
    df = pd.DataFrame(linhas, columns=colunas)
    resultado = turmas.adequar_turmas({"a.csv": df})["a.csv"]
    assert list(resultado.columns) == TURMAS_COLUNAS
    assert len(resultado) == 2
    # A última coluna bruta (c25) é descartada no corte para 23.
    assert resultado["Quantidade de Profissionais escolares"].tolist() == ["v24", "w24"]


def test_adequar_turmas_menos_colunas_quirk_do_reindex():
    colunas = ["Ordem"] + [f"c{i}" for i in range(1, 22)]  # 22 colunas
    df = pd.DataFrame([["1"] + [f"v{i}" for i in range(1, 22)]], columns=colunas)
    resultado = turmas.adequar_turmas({"a.csv": df})["a.csv"]
    assert list(resultado.columns) == TURMAS_COLUNAS
    # Quirk congelado: o reindex casa por rótulo — só "Ordem" (nome que já
    # existia) sobrevive; as 19 colunas-alvo seguintes viram NaN e as 3
    # últimas são preenchidas com "".
    assert resultado.iloc[0, 0] == "1"
    assert resultado.iloc[0, 1:20].isna().all()
    assert resultado.iloc[0, 20:].tolist() == ["", "", ""]


def test_adequar_turmas_ordem_sem_numero_descarta_ultimas_quatro():
    colunas = ["Ordem"] + [f"c{i}" for i in range(1, 25)]  # 25 colunas
    linhas = [[f"v{r}"] + [f"v{r}-{c}" for c in range(1, 25)] for r in range(10)]
    df = pd.DataFrame(linhas, columns=colunas)
    resultado = turmas.adequar_turmas({"a.csv": df})["a.csv"]
    assert len(resultado) == 6
    assert resultado["Ordem"].tolist() == ["v0", "v1", "v2", "v3", "v4", "v5"]


# ────────────────────────── alunos ───────────────────────────


def test_adequar_alunos_formata_colunas_especificas():
    df = _alunos_brutos(2)  # linhas de dados nos rótulos 15 e 16
    df.loc[15, "c1"] = '="110094711207"'
    df.loc[15, "c5"] = "5/3/2010"
    df.loc[15, "c6"] = "123"
    df.loc[16, "c1"] = "110094711208"
    df.loc[16, "c5"] = "2010-03-05"
    df.loc[16, "c6"] = "123.456.789-09"
    resultado = alunos.adequar_alunos({"a.csv": df})["a.csv"]
    assert list(resultado.columns) == ALUNOS_COLUNAS
    assert len(resultado) == 2
    assert resultado["Ordem"].tolist() == ["1", "2"]
    assert resultado["Nome"].tolist() == ["v1-4", "v2-4"]
    assert resultado["Identificação única"].tolist() == ["110094711207", "110094711208"]
    assert resultado["Data de nascimento"].tolist() == ["05/03/2010", "05/03/2010"]
    assert resultado["CPF"].tolist() == ["00000000123", "123.456.789-09"]


def test_adequar_alunos_sem_coluna_ordem_descarta_ultimas_cinco():
    colunas = [f"k{i}" for i in range(28)]
    linhas = [[f"v{r}-{c}" for c in range(28)] for r in range(8)]
    df = pd.DataFrame(linhas, columns=colunas)
    resultado = alunos.adequar_alunos({"a.csv": df})["a.csv"]
    assert list(resultado.columns) == ALUNOS_COLUNAS
    assert len(resultado) == 3
    assert resultado["Ordem"].tolist() == ["v0-0", "v1-0", "v2-0"]


# ─────────────────────── profissionais ───────────────────────


def test_adequar_profissionais_formata_colunas_especificas():
    df = _profissionais_brutos(1)  # linha de dados no rótulo 15
    df.loc[15, "c1"] = '="110094711207"'
    df.loc[15, "c5"] = "5/3/2010"
    df.loc[15, "c6"] = '="123"'
    resultado = profissionais.adequar_profissionais({"a.csv": df})["a.csv"]
    assert list(resultado.columns) == PROFISSIONAIS_COLUNAS
    assert "Data de Nascimento" in resultado.columns
    assert "Data de nascimento" not in resultado.columns  # minúsculo é só do app de alunos
    assert len(resultado) == 1
    assert resultado["Identificação única"].tolist() == ["110094711207"]
    assert resultado["Data de Nascimento"].tolist() == ["05/03/2010"]
    assert resultado["CPF"].tolist() == ["00000000123"]
