"""Smoke do PDF de documentação gerado na Tela Inicial.

Guarda de regressão: o documento tem de continuar gerando um PDF de
tamanho razoável após as edições de conteúdo da Fase 6 (grupo Adequação,
seções renumeradas, caminhos e comandos corretos).
"""

from __future__ import annotations

from apps.inicio.documentacao import build_documentacao_pdf


def test_build_documentacao_pdf_gera_bytes():
    pdf = build_documentacao_pdf()
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 10_000
