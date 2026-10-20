"""Smoke e regressão do PDF de documentação gerado na Tela Inicial.

Guardas de regressão:
- o documento tem de continuar gerando um PDF de tamanho razoável após as
  edições de conteúdo da Fase 6 (grupo Adequação, seções renumeradas,
  caminhos e comandos corretos);
- o sumário precisa ser populado (regressão: saiu vazio porque o gancho
  ``afterFlowable`` não notificava o TableOfContents);
- o rodapé paginado precisa ser desenhado nas páginas de conteúdo
  (regressão: o template "corpo" nunca era ativado, então nenhuma página
  tinha número).
"""

from __future__ import annotations

import apps.inicio.documentacao as documentacao
from apps.inicio.documentacao import build_documentacao_pdf


def test_build_documentacao_pdf_gera_bytes():
    pdf = build_documentacao_pdf()
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 10_000


def test_sumario_lista_as_secoes(monkeypatch):
    from reportlab.platypus.tableofcontents import TableOfContents

    entradas: list[tuple[str, object]] = []
    original = TableOfContents.notify

    def spy(self, eventType, content):
        entradas.append((eventType, content))
        return original(self, eventType, content)

    monkeypatch.setattr(TableOfContents, "notify", spy)
    build_documentacao_pdf()

    textos = [str(c[1]) for e, c in entradas if e == "TOCEntry"]
    assert any("1. Visão Geral do Sistema" in t for t in textos), textos[:5]
    assert any("5.1 Convenções de interface" in t for t in textos), textos[:5]
    # O próprio sumário não entra no sumário.
    assert not any(t.strip() == "Sumário" for t in textos), textos[:5]


def test_rodape_desenhado_nas_paginas_de_conteudo(monkeypatch):
    paginas: list[int] = []
    original = documentacao._rodape_pagina

    def spy(canvas, doc):
        paginas.append(doc.page)
        return original(canvas, doc)

    monkeypatch.setattr(documentacao, "_rodape_pagina", spy)
    build_documentacao_pdf()

    # A capa não tem rodapé; as páginas de conteúdo, sim.
    assert len(paginas) > 1, paginas
    assert 1 not in paginas, paginas
