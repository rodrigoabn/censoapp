from __future__ import annotations
import pandas as pd
import re


def adequar_alunos(dataframes: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Processa CSVs de alunos aplicando as seguintes adequações:

    1. Exclui as 15 primeiras linhas
    2. Exclui a 3ª e 4ª coluna (manter a 5ª)
    3. Exclui linhas de rodapé (5 linhas após última linha com número na coluna "ordem"):
       "Fonte", "Nota", "1 - Os dados", "2 - ", "Emitido"
    3. Renomeia as colunas conforme especificado (25 colunas)
    4. Padroniza formato de colunas específicas (Identificação única, Data de nascimento, CPF)

    Retorna dict {filename: df_adequado}.
    """
    novas_colunas = [
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

    resultado: dict[str, pd.DataFrame] = {}

    for nome, df in dataframes.items():
        if len(df) > 15:
            df = df.iloc[15:].reset_index(drop=True)

        if len(df.columns) >= 5:
            cols_manter = [c for i, c in enumerate(df.columns) if i not in (2, 3)]
            df = df[cols_manter]

        if "Ordem" in df.columns:
            last_data_idx = None
            for i in range(len(df) - 1, -1, -1):
                val = str(df.iloc[i]["Ordem"]).strip()
                if re.match(r"^\d+(\.\d+)?$", val):
                    last_data_idx = i
                    break
            if last_data_idx is not None:
                df = df.iloc[:last_data_idx + 1].reset_index(drop=True)
            else:
                if len(df) > 5:
                    df = df.iloc[:-5].reset_index(drop=True)
        else:
            if len(df) > 5:
                df = df.iloc[:-5].reset_index(drop=True)

        if len(df.columns) == len(novas_colunas):
            df.columns = novas_colunas
        elif len(df.columns) > len(novas_colunas):
            df = df.iloc[:, : len(novas_colunas)]
            df.columns = novas_colunas
        else:
            df = df.reindex(columns=novas_colunas[: len(df.columns)])
            for c in novas_colunas[len(df.columns) :]:
                df[c] = ""

        # ── Formatação das 3 colunas ──
        # Identificação única: remover ="..." -> texto puro
        if "Identificação única" in df.columns:
            df["Identificação única"] = (
                df["Identificação única"].astype(str).apply(_remove_aspas)
            )

        # CPF: remover ="..." e completar com zeros à esquerda até 11 dígitos
        if "CPF" in df.columns:
            df["CPF"] = (
                df["CPF"].astype(str)
                .apply(_remove_aspas)
                .apply(_completar_cpf)
            )

        # Data de nascimento: remover ="..." e normalizar para dd/mm/aaaa
        if "Data de nascimento" in df.columns:
            df["Data de nascimento"] = (
                df["Data de nascimento"]
                .astype(str)
                .apply(_remove_aspas)
                .apply(_formatar_data)
            )

        resultado[nome] = df

    return resultado


def _remove_aspas(text):
    """Remove prefixo = e aspas do início/fim. Ex.: ="110094711207" -> 110094711207."""
    if not isinstance(text, str):
        return str(text)
    if text.startswith('="'):
        text = text[2:]
    elif text.startswith('"'):
        text = text[1:]
    if text.endswith('"'):
        text = text[:-1]
    return text


_CPF_VAZIO = {"", "--", "-", "nan", "nat", "none"}


def _completar_cpf(text):
    """Completa o CPF com zeros à esquerda até 11 dígitos.

    Valores vazios ou placeholder ('--') são mantidos como estão.
    """
    if not isinstance(text, str):
        text = str(text)
    if text.strip().lower() in _CPF_VAZIO:
        return text
    digitos = re.sub(r"\D", "", text)
    if 0 < len(digitos) < 11:
        return digitos.zfill(11)
    return text


def _formatar_data(text):
    """Normaliza data para dd/mm/aaaa. Ex.: 5/3/2010 -> 05/03/2010, 2010-03-05 -> 05/03/2010."""
    if not isinstance(text, str) or text in ("", "nan", "NaT"):
        return text
    # já está dd/mm/aaaa
    if re.match(r"^\d{2}/\d{2}/\d{4}$", text):
        return text
    # d/m/aaaa ou dd/m/aaaa
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", text)
    if m:
        return f"{m.group(1).zfill(2)}/{m.group(2).zfill(2)}/{m.group(3)}"
    # yyyy-mm-dd
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", text)
    if m:
        return f"{m.group(3).zfill(2)}/{m.group(2).zfill(2)}/{m.group(1)}"
    # d-m-yyyy ou dd-mm-yyyy
    m = re.match(r"^(\d{1,2})-(\d{1,2})-(\d{4})$", text)
    if m:
        return f"{m.group(1).zfill(2)}/{m.group(2).zfill(2)}/{m.group(3)}"
    return text
