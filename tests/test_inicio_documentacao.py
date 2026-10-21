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


def _texto_do_pdf(pdf: bytes) -> str:
    """Extrai o texto do PDF (streams ASCII85+Flate; strings com escapes octais)."""
    import base64
    import re
    import zlib

    partes = []
    for bruto in re.findall(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        dados = bruto.strip()
        if dados.endswith(b"~>"):
            dados = dados[:-2]
        try:
            partes.append(zlib.decompress(base64.a85decode(dados, adobe=False)))
        except Exception:  # noqa: BLE001 — stream que não é texto
            continue
    cru = b" ".join(partes)
    textos = []
    for trecho in re.findall(rb"\((.*?)\)\s*Tj", cru, re.S):
        trecho = re.sub(
            rb"\\([0-7]{1,3})", lambda m: bytes([int(m.group(1), 8)]), trecho
        )
        textos.append(trecho.decode("latin-1"))
    return " ".join(textos)


def test_documentacao_menciona_a_coleta_de_dados_no_educacenso():
    """O manual do usuário deve descrever a nova aplicação de Coleta Automática."""
    texto = _texto_do_pdf(build_documentacao_pdf())
    assert "Visão Geral" in texto, texto[:200]
    assert "Coleta de Dados no Educacenso - 1ª Etapa" in texto, texto[:200]


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
