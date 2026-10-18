"""Pausa entre escolas configurável por ambiente (`CENSO_SLEEP_ESCOLAS`).

O default continua 0.3s; valor inválido cai no default em vez de derrubar a
coleta.
"""

from __future__ import annotations

import pytest

from apps.coleta_gestor.src import gestor_scraper
from apps.coleta_recibos_fechamento.src import receipt_scraper
from apps.coleta_relatorios.src import report_scraper
from src import scraper as cad_scraper

MODULOS = [cad_scraper, gestor_scraper, report_scraper, receipt_scraper]
IDS = ["cadastros", "gestor", "relatorios", "recibos"]


@pytest.mark.parametrize("modulo", MODULOS, ids=IDS)
def test_pausa_usa_valor_do_ambiente(monkeypatch, modulo):
    monkeypatch.setenv("CENSO_SLEEP_ESCOLAS", "1.25")

    assert modulo._pausa_entre_escolas() == 1.25


@pytest.mark.parametrize("modulo", MODULOS, ids=IDS)
def test_pausa_default_e_valor_invalido(monkeypatch, modulo):
    monkeypatch.delenv("CENSO_SLEEP_ESCOLAS", raising=False)
    assert modulo._pausa_entre_escolas() == 0.3

    monkeypatch.setenv("CENSO_SLEEP_ESCOLAS", "muito")
    assert modulo._pausa_entre_escolas() == 0.3
