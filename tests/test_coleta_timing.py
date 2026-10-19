"""Tempo por escola nos 4 coletores: log por escola + resumo final com totais.

O log `[codigo] escola processada em X.Xs` é a base do protocolo antes/depois
da Fase 5 (item 5.8); o resumo final dá o total e a média por escola da
execução. Nenhum dos dois afeta os dados coletados.
"""

from __future__ import annotations

import logging

import pytest

from apps.coleta_cadastros_escolas.src import scraper as cad_scraper
from apps.coleta_gestor.src import gestor_scraper
from apps.coleta_recibos_fechamento.src import receipt_scraper
from apps.coleta_relatorios.src import report_scraper

ESCOLAS = [{"codigo_inep": "111", "nome_unidade": "Escola Um"}]


class _PaginaFalsa:
    def close(self):
        pass


class _ContextoFalso:
    def new_page(self):
        return _PaginaFalsa()

    def clear_cookies(self):
        pass

    def close(self):
        pass


class _BrowserFalso:
    def new_context(self, **kwargs):
        return _ContextoFalso()


@pytest.fixture(autouse=True)
def _sem_espera(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)


def test_cadastros_loga_tempo_por_escola_e_resumo(monkeypatch, caplog):
    monkeypatch.setattr(cad_scraper, "_login_and_read", lambda *a, **k: None)
    monkeypatch.setattr(cad_scraper, "_session_expirada", lambda page: False)
    monkeypatch.setattr(cad_scraper, "scrape_school", lambda page, codigo, nome: {"Ficha": {}})

    with caplog.at_level(logging.INFO):
        outputs, failures = cad_scraper.run_scraping(_BrowserFalso(), "l", "s", ESCOLAS)

    assert len(outputs) == 1
    assert failures == []
    assert "[111] escola processada em" in caplog.text
    assert "1 escola(s) coletada(s)" in caplog.text


def test_gestor_loga_tempo_por_escola_e_resumo(monkeypatch, caplog):
    monkeypatch.setattr(gestor_scraper, "_login_and_read", lambda *a, **k: None)
    monkeypatch.setattr(gestor_scraper, "_session_expirada", lambda page: False)
    monkeypatch.setattr(
        gestor_scraper, "scrape_gestor_school", lambda page, codigo, nome: {"Vínculo do gestor": {}}
    )

    with caplog.at_level(logging.INFO):
        outputs, failures = gestor_scraper.run_scraping(_BrowserFalso(), "l", "s", ESCOLAS)

    assert len(outputs) == 1
    assert failures == []
    assert "[111] escola processada em" in caplog.text
    assert "1 escola(s) coletada(s)" in caplog.text


def test_relatorios_loga_tempo_por_escola_e_resumo(monkeypatch, caplog):
    monkeypatch.setattr(report_scraper, "_login_and_read", lambda *a, **k: None)
    monkeypatch.setattr(report_scraper, "_session_expirada", lambda page: False)
    monkeypatch.setattr(report_scraper, "_select_school", lambda page, codigo: True)
    monkeypatch.setattr(report_scraper, "_download_report_csv", lambda page, url: b"csv")

    with caplog.at_level(logging.INFO):
        outputs, failures = report_scraper.run_report_scraping(
            _BrowserFalso(), "l", "s", ESCOLAS, "https://exemplo/relatorio"
        )

    assert len(outputs) == 1
    assert failures == []
    assert "[111] escola processada em" in caplog.text
    assert "1 escola(s) coletada(s)" in caplog.text


def test_recibos_loga_tempo_por_escola_e_resumo(monkeypatch, caplog):
    monkeypatch.setattr(receipt_scraper, "_login_and_read", lambda *a, **k: None)
    monkeypatch.setattr(receipt_scraper, "_session_expirada", lambda page: False)
    monkeypatch.setattr(receipt_scraper, "_select_school", lambda page, codigo: True)
    monkeypatch.setattr(receipt_scraper, "_download_receipt_pdf", lambda *a, **k: b"pdf")

    with caplog.at_level(logging.INFO):
        outputs, failures = receipt_scraper.run_receipt_scraping(
            _BrowserFalso(), "l", "s", ESCOLAS, "https://exemplo/fechamento"
        )

    assert len(outputs) == 1
    assert failures == []
    assert "[111] escola processada em" in caplog.text
    assert "1 escola(s) coletada(s)" in caplog.text
