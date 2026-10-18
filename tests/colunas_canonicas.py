"""Snapshots das listas canônicas de colunas-alvo (turmas/aluno/profissionais).

Retratos literais das `novas_colunas` internas dos processadores de adequação
(`apps/adequacao_*/src/processor.py` — listas locais à função, não importáveis),
usados por dois testes:

- `tests/test_adequacao_processors.py`: a saída de cada processador termina
  exatamente nestas colunas;
- `tests/rules/test_validations.py`: o `expected_columns` do registro
  `VALIDATIONS` é **idêntico** (conteúdo e ordem) a estas listas — as apps de
  adequação e de verificação precisam concordar sobre as colunas.

Mudar qualquer um dos lados exige atualizar este arquivo: é o canário de
deriva entre as apps (a Fase 4 — `apps/common` — depende desta concordância).
"""

from __future__ import annotations

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
