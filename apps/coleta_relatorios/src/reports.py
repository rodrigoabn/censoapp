"""Configuração das 3 aplicações de coleta de relatórios do Educacenso.

Cada relatório compartilha o mesmo fluxo (login, seleção da escola, geração e
download do CSV nativo do site). O que muda é apenas o nome exibido e a URL do
relatório. Este dicionário parametriza o frontend e o scraper.
"""

from __future__ import annotations

from .auth import BASE_URL

_REL_BASE = f"{BASE_URL}/relatorio/escola/relacao-escola"

REPORTS: dict[str, dict] = {
    "turmas": {
        "key": "turmas",
        "state_prefix": "rt_",
        "title": "Relatórios de Turmas",
        "subtitle": "Baixa o relatório de turmas de cada escola no Educacenso, "
        "em modo leitura (não altera dados no site).",
        "url": f"{_REL_BASE}/relacao-turma-escola",
        "zip_prefix": "relatorio_turmas",
    },
    "alunos": {
        "key": "alunos",
        "state_prefix": "ra_",
        "title": "Relatórios de Alunos",
        "subtitle": "Baixa o relatório de alunos de cada escola no Educacenso, "
        "em modo leitura (não altera dados no site).",
        "url": f"{_REL_BASE}/relacao-aluno-escola",
        "zip_prefix": "relatorio_alunos",
    },
    "profissionais": {
        "key": "profissionais",
        "state_prefix": "rp_",
        "title": "Relatórios de Profissionais Escolares",
        "subtitle": "Baixa o relatório de profissionais escolares de cada escola "
        "no Educacenso, em modo leitura (não altera dados no site).",
        "url": f"{_REL_BASE}/relacao-profissional-escola",
        "zip_prefix": "relatorio_profissionais",
    },
}
