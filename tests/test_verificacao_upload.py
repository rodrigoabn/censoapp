"""Testes golden de `src/upload.py` — leitura de escolas e ZIPs do Educacenso.

Pina o comportamento atual da leitura: heurística de cabeçalho
(`_find_column`), tolerância de planilha de escolas, montagem do unificado a
partir dos CSVs do ZIP e as divisões por tipo (turmas, profissionais, aluno).

Observações pinadas:

- `_find_column` tenta igualdade (caixa/espaços ignorados) antes de substring.
- Uma "linha de título" (≤ 3 células preenchidas) é pulada no CSV; por isso os
  CSVs dos testes têm 4+ colunas — cabeçalhos de 3 colunas seriam pulados.
- `read_turmas_zip` deriva `periodo_turma`/`verifica_integral` **apenas** em
  `turmas_escolarizacao`; a escolarização inclui também as curriculares
  (`~(AEE | atividade complementar)`).
- `read_aluno_zip`: `aluno_curricular` = fora de AEE/ATV; `aluno_deficiencia`
  exige deficiência **ou** transtorno e exclui as linhas "Não se aplica".
"""

from __future__ import annotations

import io
import zipfile

import pytest

from apps.verificacao_inconsistencias.src.upload import (
    _eh_linha_titulo,
    _extrair_codigo_nome,
    _find_column,
    checar_colunas,
    read_aluno_zip,
    read_profissionais_zip,
    read_school_list,
    read_turmas_zip,
    read_zip_merged,
)

# ─────────────────────────── helpers ───────────────────────────


def _zip_bytes(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content.encode("utf-8"))
    return buffer.getvalue()


# ─────────────────────── _find_column ──────────────────────────


_FIND_COLUMN = [
    pytest.param(["Código do Inep"], "código do inep", "Código do Inep", id="exato-caixa"),
    pytest.param([" cóDIGO do INEP "], "código do inep", " cóDIGO do INEP ", id="exato-espacos"),
    pytest.param(["Codigo do Inep"], "código do inep", None, id="acento-nao-e-ignorado"),
    pytest.param(["Codigo do Inep"], "codigo do inep", "Codigo do Inep", id="fallback-sem-acento"),
    pytest.param(["Código do Inep *"], "código do inep", "Código do Inep *", id="substring"),
    pytest.param(
        ["Nome da Unidade Escolar", "Nome da Unidade"], "nome da unidade",
        "Nome da Unidade", id="exato-vence-substring",
    ),
    pytest.param(["Outra", "Sem relação"], "código do inep", None, id="ausente"),
]


@pytest.mark.parametrize("colunas,procurada,esperado", _FIND_COLUMN)
def test_find_column(colunas, procurada, esperado):
    assert _find_column(colunas, procurada) == esperado


# ───────────────────── _extrair_codigo_nome ────────────────────


_EXTRAIR = [
    pytest.param("12345_Nome da Escola.csv", ("12345", "Nome da Escola"), id="codigo-nome"),
    pytest.param("12345.csv", ("12345", ""), id="so-codigo"),
    pytest.param("pasta/sub/12345_Escola.csv", ("12345", "Escola"), id="com-diretorio"),
    pytest.param("1_Escola_A_B.csv", ("1", "Escola_A_B"), id="underscores-extras"),
    pytest.param("sem_ext_xlsx.xlsx", ("sem", "ext_xlsx"), id="extensao-removida"),
]


@pytest.mark.parametrize("filename,esperado", _EXTRAIR)
def test_extrair_codigo_nome(filename, esperado):
    assert _extrair_codigo_nome(filename) == esperado


# ────────────────────── _eh_linha_titulo ───────────────────────


_EH_TITULO = [
    pytest.param("", True, id="vazia"),
    pytest.param(";;;", True, id="so-separadores"),
    pytest.param("A;B;C", True, id="tres-preenchidas"),
    pytest.param(";;Título;;", True, id="uma-preenchida"),
    pytest.param("A;B;C;D", False, id="quatro-preenchidas"),
    pytest.param("Ordem;Código;Nome;X;Y", False, id="linha-normal"),
]


@pytest.mark.parametrize("linha,esperado", _EH_TITULO)
def test_eh_linha_titulo(linha, esperado):
    assert _eh_linha_titulo(linha) is esperado


# ─────────────────────── read_school_list ──────────────────────


def test_read_school_list_basico(wb_bytes):
    data = wb_bytes({"Escolas": [
        ["Código do Inep", "Nome da Unidade"],
        ["123", "Escola A"],
        ["456", "Escola B"],
    ]})
    assert read_school_list(io.BytesIO(data)) == [
        {"codigo_inep": "123", "nome_unidade": "Escola A"},
        {"codigo_inep": "456", "nome_unidade": "Escola B"},
    ]


def test_read_school_list_tolera_caixa_e_espacos_no_cabecalho(wb_bytes):
    data = wb_bytes({"Escolas": [
        ["CÓDIGO DO INEP", "Nome Da Unidade"],
        ["123", "Escola A"],
    ]})
    assert read_school_list(io.BytesIO(data)) == [
        {"codigo_inep": "123", "nome_unidade": "Escola A"},
    ]


def test_read_school_list_ignora_linhas_sem_codigo(wb_bytes):
    data = wb_bytes({"Escolas": [
        ["Código do Inep", "Nome da Unidade"],
        ["", "Escola sem código"],
        ["123", "Escola A"],
    ]})
    assert read_school_list(io.BytesIO(data)) == [
        {"codigo_inep": "123", "nome_unidade": "Escola A"},
    ]


def test_read_school_list_ignora_codigo_placeholder_textual(wb_bytes):
    data = wb_bytes({"Escolas": [
        ["Código do Inep", "Nome da Unidade"],
        ["nan", "Placeholder nan"],
        ["none", "Placeholder none"],
        ["456", "Escola B"],
    ]})
    assert read_school_list(io.BytesIO(data)) == [
        {"codigo_inep": "456", "nome_unidade": "Escola B"},
    ]


def test_read_school_list_nome_vazio_vira_string_vazia(wb_bytes):
    data = wb_bytes({"Escolas": [
        ["Código do Inep", "Nome da Unidade"],
        ["123", ""],
    ]})
    assert read_school_list(io.BytesIO(data)) == [
        {"codigo_inep": "123", "nome_unidade": ""},
    ]


def test_read_school_list_sem_coluna_nome(wb_bytes):
    data = wb_bytes({"Escolas": [["Código do Inep"], ["123"]]})
    assert read_school_list(io.BytesIO(data)) == [
        {"codigo_inep": "123", "nome_unidade": ""},
    ]


def test_read_school_list_erro_sem_coluna_codigo(wb_bytes):
    data = wb_bytes({"Escolas": [["Nome da Unidade"], ["Escola A"]]})
    with pytest.raises(ValueError) as excinfo:
        read_school_list(io.BytesIO(data))
    assert str(excinfo.value).startswith("Coluna 'código do inep' não encontrada no arquivo.")


# ───────────────────────── checar_colunas ──────────────────────


def test_checar_colunas_identicas(df):
    ok, faltando, extras = checar_colunas(df({"A": [1], "B": [2]}), ["A", "B"])
    assert (ok, faltando, extras) == (True, [], [])


def test_checar_colunas_divergentes_preserva_ordem(df):
    ok, faltando, extras = checar_colunas(df({"B": [1], "C": [2]}), ["A", "B"])
    assert (ok, faltando, extras) == (False, ["A"], ["C"])


def test_checar_colunas_ignora_colunas_internas(df):
    dados = df({"Código do Inep": [1], "Nome da Unidade": [2], "A": [3]})
    assert checar_colunas(dados, ["A"]) == (True, [], [])


# ──────────────────────── read_zip_merged ──────────────────────

_CSV_4COL = "A;B;C;D\n1;2;3;4\n"


def test_read_zip_merged_concatena_e_extrai_codigo_nome():
    raw = _zip_bytes({
        "123_Escola A.csv": "A;B;C;D\n1;2;3;4\n",
        "456_Escola B.csv": "A;B;C;D\n5;6;7;8\n",
    })
    dados = read_zip_merged(raw)
    assert dados["csv_count"] == 2
    assert list(dados["unificado"].columns) == ["Código do Inep", "Nome da Unidade", "A", "B", "C", "D"]
    assert dados["unificado"]["Código do Inep"].tolist() == ["123", "456"]
    assert dados["unificado"]["Nome da Unidade"].tolist() == ["Escola A", "Escola B"]
    assert dados["escolas"] == [
        {"Código do Inep": "123", "Nome da Unidade": "Escola A"},
        {"Código do Inep": "456", "Nome da Unidade": "Escola B"},
    ]


def test_read_zip_merged_pula_linha_de_titulo():
    raw = _zip_bytes({"123_Escola A.csv": ";;;\n" + _CSV_4COL})
    dados = read_zip_merged(raw)
    assert list(dados["unificado"].columns) == ["Código do Inep", "Nome da Unidade", "A", "B", "C", "D"]
    assert dados["unificado"].iloc[0]["A"] == "1"


def test_read_zip_merged_remove_bom_utf8():
    raw = _zip_bytes({"123_Escola A.csv": "\ufeff" + _CSV_4COL})
    assert "A" in read_zip_merged(raw)["unificado"].columns


def test_read_zip_merged_ignora_arquivos_nao_csv():
    raw = _zip_bytes({"123_Escola A.csv": _CSV_4COL, "leia-me.txt": "nada"})
    assert read_zip_merged(raw)["csv_count"] == 1


def test_read_zip_merged_sem_csv_levanta_erro():
    raw = _zip_bytes({"leia-me.txt": "nada"})
    with pytest.raises(ValueError) as excinfo:
        read_zip_merged(raw)
    assert str(excinfo.value) == "Nenhum arquivo CSV encontrado dentro do ZIP."


def test_read_zip_merged_escolas_deduplicadas():
    raw = _zip_bytes({"123_Escola A.csv": "A;B;C;D\n1;2;3;4\n5;6;7;8\n"})
    assert read_zip_merged(raw)["escolas"] == [
        {"Código do Inep": "123", "Nome da Unidade": "Escola A"},
    ]


def test_read_zip_merged_nome_ausente_no_arquivo():
    raw = _zip_bytes({"123.csv": _CSV_4COL})
    assert read_zip_merged(raw)["escolas"] == [
        {"Código do Inep": "123", "Nome da Unidade": ""},
    ]


# ───────────────────────── read_turmas_zip ─────────────────────

_CSV_TURMAS = (
    "Tipo de turma;Etapa Agregada;Nome da turma;Extra\n"
    "Atendimento educacional especializado (AEE);-;9AM09;x\n"
    "Atividade complementar;-;8AM08;x\n"
    "Curricular (etapa de ensino);Ensino Fundamental;2BM02;x\n"
    "Outro tipo;Ensino Fundamental;3CM03;x\n"
)


def test_read_turmas_zip_divide_e_deriva_colunas():
    dados = read_turmas_zip(_zip_bytes({"123_Escola A.csv": _CSV_TURMAS}))
    assert dados["turmas_aee"]["Nome da turma"].tolist() == ["9AM09"]
    assert dados["turmas_atvcomplementar"]["Nome da turma"].tolist() == ["8AM08"]
    assert dados["turmas_curricular"]["Nome da turma"].tolist() == ["2BM02"]
    # Escolarização = tudo que não é AEE nem atividade complementar (inclui
    # as curriculares).
    assert dados["turmas_escolarizacao"]["Nome da turma"].tolist() == ["2BM02", "3CM03"]
    assert dados["turmas_escolarizacao"]["periodo_turma"].tolist() == ["2B", "3C"]
    assert dados["turmas_escolarizacao"]["verifica_integral"].tolist() == ["M", "M"]


def test_read_turmas_zip_exige_tipo_de_turma():
    raw = _zip_bytes({"123_Escola A.csv": "Etapa Agregada;Nome da turma;X;Y\n-;1AM01;1;2\n"})
    with pytest.raises(ValueError) as excinfo:
        read_turmas_zip(raw)
    assert str(excinfo.value).startswith("Coluna 'Tipo de turma' não encontrada nos CSVs.")


# ───────────────────── read_profissionais_zip ──────────────────

_CSV_PROF = (
    "Etapa de ensino;Nome;X;Y\n"
    "Não se aplica;Ana;1;2\n"
    "Ensino fundamental de 9 anos - 1º Ano;Bruno;3;4\n"
)


def test_read_profissionais_zip_divide_por_etapa():
    dados = read_profissionais_zip(_zip_bytes({"123_Escola A.csv": _CSV_PROF}))
    assert dados["prof_aee_atv"]["Nome"].tolist() == ["Ana"]
    assert dados["prof_curricular"]["Nome"].tolist() == ["Bruno"]


def test_read_profissionais_zip_exige_etapa_de_ensino():
    raw = _zip_bytes({"123_Escola A.csv": "Nome;X;Y;Z\nAna;1;2;3\n"})
    with pytest.raises(ValueError) as excinfo:
        read_profissionais_zip(raw)
    assert str(excinfo.value).startswith("Coluna 'Etapa de ensino' não encontrada nos CSVs.")


# ────────────────────────── read_aluno_zip ─────────────────────

_CSV_ALUNO = (
    "Etapa de ensino;"
    "Tipo de atendimento educacional especializado (AEE);"
    "Transporte escolar (Sim/Não);"
    "Tipo(s) de deficiência(s), transtorno(s) do espectro autista e altas habilidades ou superdotação;"
    "Tipo(s) de transtorno(s) que impacta(m) o desenvolvimento da aprendizagem;"
    "Nome;Extra\n"
    "Não se aplica;Sim;Não;Cegueira;--;Ana;x\n"
    "Não se aplica;--;Sim;--;--;Bruno;x\n"
    "Ensino fundamental de 9 anos - 1º Ano;--;Não;Baixa visão;--;Carla;x\n"
    "Ensino fundamental de 9 anos - 1º Ano;--;Não;--;TDAH;Davi;x\n"
    "Ensino fundamental de 9 anos - 1º Ano;--;Não;--;--;Elisa;x\n"
)


def test_read_aluno_zip_divide():
    dados = read_aluno_zip(_zip_bytes({"123_Escola A.csv": _CSV_ALUNO}))
    assert dados["aluno_curricular"]["Nome"].tolist() == ["Carla", "Davi", "Elisa"]
    assert dados["aluno_aee"]["Nome"].tolist() == ["Ana"]
    assert dados["aluno_atv"]["Nome"].tolist() == ["Bruno"]
    assert dados["aluno_transporte"]["Nome"].tolist() == ["Bruno"]
    # Ana tem deficiência registrada, mas está fora ("Não se aplica" exclui).
    assert dados["aluno_deficiencia"]["Nome"].tolist() == ["Carla", "Davi"]


def test_read_aluno_zip_exige_etapa_de_ensino():
    raw = _zip_bytes({"123_Escola A.csv": "Nome;X;Y;Z\nAna;1;2;3\n"})
    with pytest.raises(ValueError) as excinfo:
        read_aluno_zip(raw)
    assert str(excinfo.value).startswith("Coluna 'Etapa de ensino' não encontrada nos CSVs.")


def test_read_aluno_zip_exige_coluna_seguinte_na_ordem():
    # Com "Etapa de ensino" presente, a próxima exigida é a de AEE.
    raw = _zip_bytes({"123_Escola A.csv": "Etapa de ensino;Nome;X;Y\nNão se aplica;Ana;1;2\n"})
    with pytest.raises(ValueError) as excinfo:
        read_aluno_zip(raw)
    assert str(excinfo.value).startswith(
        "Coluna 'Tipo de atendimento educacional especializado (AEE)' não encontrada"
    )
