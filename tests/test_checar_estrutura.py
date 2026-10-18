"""Testes golden de `src/checar_estrutura.py` — comparação de cabeçalhos.

Pina o contrato de `checar_estrutura`: leitura só da primeira linha de cada
aba (com aparo de células vazias à direita), comparação de abas por conjunto,
colunas por posição/igualdade e o formato exato das mensagens.

Observações pinadas:

- A ordem das mensagens é: abas faltando, abas extras e, por aba em comum em
  ordem alfabética, a divergência de colunas seguida das colunas linha a linha.
- Referência ilegível tem prioridade: o erro do arquivo de referência é
  retornado antes de qualquer tentativa de ler o enviado.
- A comparação de nomes de coluna diferencia caixa.
"""

from __future__ import annotations

from apps.verificacao_inconsistencias.src.checar_estrutura import checar_estrutura

REF = {"Painel": [["A", "B", "C"]]}


def test_identico_passa(wb_bytes):
    assert checar_estrutura(wb_bytes(REF), wb_bytes(REF)) == (True, [])


def test_abas_em_ordem_diferente_passa(wb_bytes):
    ref = {"Aba A": [["X", "Y"]], "Aba B": [["Z", "W"]]}
    upl = {"Aba B": [["Z", "W"]], "Aba A": [["X", "Y"]]}
    assert checar_estrutura(wb_bytes(upl), wb_bytes(ref)) == (True, [])


def test_aba_faltando(wb_bytes):
    ref = {"Painel": [["A", "B", "C"]], "Relatório": [["X"]]}
    ok, erros = checar_estrutura(wb_bytes(REF), wb_bytes(ref))
    assert ok is False
    assert erros == ["Abas faltando no arquivo: ['Relatório']"]


def test_aba_extra(wb_bytes):
    upl = {"Painel": [["A", "B", "C"]], "Extra": [["X"]]}
    ok, erros = checar_estrutura(wb_bytes(upl), wb_bytes(REF))
    assert ok is False
    assert erros == ["Abas não esperadas no arquivo: ['Extra']"]


def test_coluna_divergente(wb_bytes):
    upl = {"Painel": [["A", "X", "C"]]}
    ok, erros = checar_estrutura(wb_bytes(upl), wb_bytes(REF))
    assert ok is False
    assert erros == [
        "Aba 'Painel': colunas divergem do esperado. Esperado 3 coluna(s), encontrado 3 coluna(s).",
        "  Coluna 2: esperado 'B', encontrado 'X'",
    ]


def test_coluna_extra_no_fim(wb_bytes):
    upl = {"Painel": [["A", "B", "C", "D"]]}
    ok, erros = checar_estrutura(wb_bytes(upl), wb_bytes(REF))
    assert ok is False
    assert erros == [
        "Aba 'Painel': colunas divergem do esperado. Esperado 3 coluna(s), encontrado 4 coluna(s).",
        "  Coluna 4: extra 'D'",
    ]


def test_coluna_faltando_no_fim(wb_bytes):
    upl = {"Painel": [["A", "B"]]}
    ok, erros = checar_estrutura(wb_bytes(upl), wb_bytes(REF))
    assert ok is False
    assert erros == [
        "Aba 'Painel': colunas divergem do esperado. Esperado 3 coluna(s), encontrado 2 coluna(s).",
        "  Coluna 3: esperado 'C' — faltando",
    ]


def test_caixa_diferencia(wb_bytes):
    ref = {"Painel": [["a"]]}
    upl = {"Painel": [["A"]]}
    ok, erros = checar_estrutura(wb_bytes(upl), wb_bytes(ref))
    assert ok is False
    assert erros == [
        "Aba 'Painel': colunas divergem do esperado. Esperado 1 coluna(s), encontrado 1 coluna(s).",
        "  Coluna 1: esperado 'a', encontrado 'A'",
    ]


def test_celulas_vazias_a_direita_sao_aparadas(wb_bytes):
    upl = {"Painel": [["A", "B", ""]]}
    assert checar_estrutura(wb_bytes(upl), wb_bytes(REF | {"Painel": [["A", "B"]]})) == (True, [])


def test_ordem_das_mensagens(wb_bytes):
    ref = {"Painel": [["A", "B"]], "Sumário": [["S"]]}
    upl = {"Painel": [["A", "X"]], "Extra": [["E"]]}
    ok, erros = checar_estrutura(wb_bytes(upl), wb_bytes(ref))
    assert ok is False
    assert erros == [
        "Abas faltando no arquivo: ['Sumário']",
        "Abas não esperadas no arquivo: ['Extra']",
        "Aba 'Painel': colunas divergem do esperado. Esperado 2 coluna(s), encontrado 2 coluna(s).",
        "  Coluna 2: esperado 'B', encontrado 'X'",
    ]


def test_referencia_ilegivel(wb_bytes):
    ok, erros = checar_estrutura(wb_bytes(REF), b"isto nao e um xlsx")
    assert ok is False
    assert len(erros) == 1
    assert erros[0].startswith("Não foi possível ler o arquivo de referência: ")


def test_enviado_ilegivel(wb_bytes):
    ok, erros = checar_estrutura(b"isto nao e um xlsx", wb_bytes(REF))
    assert ok is False
    assert len(erros) == 1
    assert erros[0].startswith("Não foi possível ler o arquivo enviado: ")


def test_erro_da_referencia_tem_prioridade():
    ok, erros = checar_estrutura(b"enviado invalido", b"referencia invalida")
    assert ok is False
    assert len(erros) == 1
    assert erros[0].startswith("Não foi possível ler o arquivo de referência: ")
