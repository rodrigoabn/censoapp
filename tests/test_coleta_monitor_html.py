"""Monitores de coleta não devem permitir HTML injetado pelo XLSX de entrada."""

from __future__ import annotations

from apps.coleta_recibos_fechamento.src import frontend as rec_frontend
from apps.coleta_relatorios.src import frontend as rel_frontend


def test_linha_monitor_de_relatorios_escapa_html():
    linha = rel_frontend._linha_monitor("Escola <b>X</b> & Cia", "#b2b5be")
    assert linha == "<span style='color:#b2b5be'>Escola &lt;b&gt;X&lt;/b&gt; &amp; Cia</span>"


def test_linha_monitor_de_recibos_escapa_html():
    linha = rec_frontend._linha_monitor('Escola "Y" <script>', "#6e6e6e")
    assert linha == "<span style='color:#6e6e6e'>Escola &quot;Y&quot; &lt;script&gt;</span>"
