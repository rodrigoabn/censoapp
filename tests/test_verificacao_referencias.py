"""Pina as referências de estrutura versionadas do app de verificação.

`checar_estrutura` compara o upload do usuário com arquivos de referência
carregados em `frontend._REFERENCIA_BYTES`. Sem referências no repositório a
checagem era silenciosamente inerte (bytes `None`); este teste garante que:

- as referências existem e carregam;
- a saída **atual** dos coletores (a mesma função `build_xlsx` que gera o
  XLSX da coleta, aqui executada sem CSVs temporários) passa na checagem;
- um arquivo de outra tela (conjunto de abas diferente) falha com erro.
"""

from __future__ import annotations

from apps.coleta_cadastros_escolas.src.exporter import build_xlsx as build_unidades
from apps.coleta_gestor.src.exporter import build_xlsx as build_gestor
from apps.verificacao_inconsistencias.src import frontend
from apps.verificacao_inconsistencias.src.checar_estrutura import checar_estrutura


def test_referencias_carregam():
    assert frontend._REFERENCIA_BYTES["unidades"] is not None
    assert frontend._REFERENCIA_BYTES["gestor"] is not None


def test_saida_atual_dos_coletores_passa_na_referencia(tmp_path):
    refs = frontend._REFERENCIA_BYTES
    assert checar_estrutura(build_unidades(tmp_path / "u"), refs["unidades"]) == (True, [])
    assert checar_estrutura(build_gestor(tmp_path / "g"), refs["gestor"]) == (True, [])


def test_arquivo_de_outra_tela_falha():
    refs = frontend._REFERENCIA_BYTES
    ok, erros = checar_estrutura(refs["gestor"], refs["unidades"])
    assert ok is False
    assert erros
