from __future__ import annotations

import pandas as pd
import re


def adequar_turmas(dataframes: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Processa CSVs de turmas aplicando as seguintes adequações:

    1. Exclui as 14 primeiras linhas
    2. Exclui a 3ª e 5ª coluna
    3. Exclui linhas de rodópole (últimas 4 linhas que começam com:
       "Fonte", "Nota", "1 - Os dados", "Emitido")
    4. Renomeia as colunas conforme especificado

    Retorna dict {filename: df_adequado}.
    """
    # Novo nome das colunas em ordem
    novas_colunas = [
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

    resultado: dict[str, pd.DataFrame] = {}

    for nome, df in dataframes.items():
        # --- Passo 1: Remover as 14 primeiras linhas ---
        # O CSV já vem lido pelo pandas; removemos as 14 primeiras linhas de dados
        # (considerando que header foi lido corretamente). Se o CSV tem 14 linhas
        # antes do header real, precisamos lidar com isso.
        # Aqui assumimos que df já tem o header como coluna e removemos as 14 primeiras linhas de dados.
        if len(df) > 14:
            df = df.iloc[14:].reset_index(drop=True)

        # --- Passo 2: Excluir a 3ª e 5ª coluna (1-indexed) ---
        # Em 0-indexed: colunas 2 e 4
        if len(df.columns) >= 5:
            cols_manter = [c for i, c in enumerate(df.columns) if i not in (2, 4)]
            df = df[cols_manter]

        # --- Passo 3: Excluir linhas de rodapé ---
        # As 4 últimas linhas começam com: "Fonte", "Nota", "1 - Os dados", "Emitido"
        # Identificamos o índice da última linha cujo valor da coluna "Ordem" seja um número
        # (ou seja, a última linha de dados verdadeira antes do rodópole).

        # Verificar se a coluna "Ordem" existe
        if "Ordem" in df.columns:
            # Procurar a última linha onde "Ordem" parece ser número
            last_data_idx = None
            for i in range(len(df) - 1, -1, -1):
                val = str(df.iloc[i]["Ordem"]).strip()
                # Se contém apenas dígitos (ou dígitos com pontos/índices como "1.1"), considera como dado
                if re.match(r"^\d+(\.\d+)?$", val):
                    last_data_idx = i
                    break

            if last_data_idx is not None:
                # Manter apenas linhas até o último dado (inclusive)
                df = df.iloc[: last_data_idx + 1].reset_index(drop=True)
            else:
                # Se não encontrar, remover as 4 últimas linhas (rodópole)
                if len(df) > 4:
                    df = df.iloc[:-4].reset_index(drop=True)
        else:
            # Se não tem coluna Ordem, remover 4 últimas linhas
            if len(df) > 4:
                df = df.iloc[:-4].reset_index(drop=True)

        # --- Passo 4: Renomear colunas ---
        # Se o número de colunas corresponder, renomeamos
        if len(df.columns) == len(novas_colunas):
            df.columns = novas_colunas
        elif len(df.columns) > len(novas_colunas):
            # Manter apenas as primeiras N colunas
            df = df.iloc[:, : len(novas_colunas)]
            df.columns = novas_colunas
        else:
            # Se tiver menos colunas, preencher com o que sobrou
            # (não deve acontecer com os dados corretos, mas por segurança)
            df = df.reindex(columns=novas_colunas[: len(df.columns)])
            # Preencher colunas faltantes com ""
            for c in novas_colunas[len(df.columns) :]:
                df[c] = ""

        resultado[nome] = df

    return resultado