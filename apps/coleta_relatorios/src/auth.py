"""Configuração de acesso ao Educacenso (MODO LEITURA).

Aplicação ESTRITAMENTE em modo leitura: apenas NAVEGA, PREENCHE os campos
de login/senha para ACESSAR o sistema e BAIXA os relatórios (CSV) que o
próprio Educacenso disponibiliza. Nenhum dado do site é alterado, nenhum
formulário de questionário é submetido/salvo.
"""

from apps.common.auth import BASE_URL, READ_ONLY, _assert_read_only  # noqa: F401
