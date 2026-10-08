"""Configuração de acesso ao Educacenso (MODO LEITURA).

Aplicação ESTRITAMENTE em modo leitura: apenas NAVEGA, PREENCHE os campos
de login/senha para ACESSAR o sistema e BAIXA os relatórios (CSV) que o
próprio Educacenso disponibiliza. Nenhum dado do site é alterado, nenhum
formulário de questionário é submetido/salvo.
"""

from __future__ import annotations

# URL base do sistema Educacenso.
BASE_URL = "https://educacenso.inep.gov.br"

# Guarda invariante do modo leitura. Qualquer tentativa de escrita no site
# deve ser bloqueada por esta flag.
READ_ONLY = True


def _assert_read_only() -> None:
    if not READ_ONLY:
        raise RuntimeError("MODO LEITURA violado: operações de escrita no site estão proibidas.")
