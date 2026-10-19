"""Escrita incremental por escola: callback `on_school_done` nos 4 coletores.

O callback grava cada escola assim que ela termina, ANTES do `append` no
retorno: se a gravação falhar, a exceção vira falha da escola ("não
coletadas") — nada some em silêncio. Os frontends passam o callback e não
fazem mais o loop pós-coleta (que duplicaria a gravação).
"""

from __future__ import annotations

import threading

import pytest

from apps.coleta_cadastros_escolas.src import exporter as cad_exporter
from apps.coleta_cadastros_escolas.src import frontend as cad_frontend
from apps.coleta_cadastros_escolas.src import modelo as cad_modelo
from apps.coleta_cadastros_escolas.src import scraper as cad_scraper
from apps.coleta_gestor.src import exporter as ges_exporter
from apps.coleta_gestor.src import frontend as ges_frontend
from apps.coleta_gestor.src import gestor_scraper
from apps.coleta_gestor.src import modelo as ges_modelo
from apps.coleta_recibos_fechamento.src import frontend as rec_frontend
from apps.coleta_recibos_fechamento.src import receipt_scraper
from apps.coleta_relatorios.src import frontend as rel_frontend
from apps.coleta_relatorios.src import report_scraper

ESCOLAS = [
    {"codigo_inep": "111", "nome_unidade": "Escola Um"},
    {"codigo_inep": "222", "nome_unidade": "Escola Dois"},
]


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

    def close(self):
        pass


@pytest.fixture(autouse=True)
def _sem_espera(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)


def _preparar_cadastros(monkeypatch):
    monkeypatch.setattr(cad_scraper, "_login_and_read", lambda *a, **k: None)
    monkeypatch.setattr(cad_scraper, "_session_expirada", lambda page: False)
    monkeypatch.setattr(cad_scraper, "scrape_school", lambda page, codigo, nome: {"Ficha": {}})


def _preparar_gestor(monkeypatch):
    monkeypatch.setattr(gestor_scraper, "_login_and_read", lambda *a, **k: None)
    monkeypatch.setattr(gestor_scraper, "_session_expirada", lambda page: False)
    monkeypatch.setattr(
        gestor_scraper, "scrape_gestor_school", lambda page, codigo, nome: {"Vínculo do gestor": {}}
    )


def _preparar_relatorios(monkeypatch):
    monkeypatch.setattr(report_scraper, "_login_and_read", lambda *a, **k: None)
    monkeypatch.setattr(report_scraper, "_session_expirada", lambda page: False)
    monkeypatch.setattr(report_scraper, "_select_school", lambda page, codigo: True)
    monkeypatch.setattr(report_scraper, "_download_report_csv", lambda page, url: b"csv")


def _preparar_recibos(monkeypatch):
    monkeypatch.setattr(receipt_scraper, "_login_and_read", lambda *a, **k: None)
    monkeypatch.setattr(receipt_scraper, "_session_expirada", lambda page: False)
    monkeypatch.setattr(receipt_scraper, "_select_school", lambda page, codigo: True)
    monkeypatch.setattr(receipt_scraper, "_download_receipt_pdf", lambda *a, **k: b"pdf")


# ── scrapers: callback chamado na ordem × falha do callback ────────────────


def test_cadastros_callback_recebe_escolas_na_ordem(monkeypatch):
    _preparar_cadastros(monkeypatch)
    gravadas = []

    outputs, failures = cad_scraper.run_scraping(
        _BrowserFalso(), "l", "s", ESCOLAS,
        on_school_done=lambda escola, dados: gravadas.append(escola["codigo_inep"]),
    )

    assert gravadas == ["111", "222"]
    assert [e["codigo_inep"] for e, _ in outputs] == ["111", "222"]
    assert failures == []


def test_cadastros_falha_do_callback_vira_nao_coletada(monkeypatch):
    _preparar_cadastros(monkeypatch)

    def _boom(escola, dados):
        raise RuntimeError("boom")

    outputs, failures = cad_scraper.run_scraping(
        _BrowserFalso(), "l", "s", ESCOLAS[:1], on_school_done=_boom,
    )

    assert outputs == []
    assert len(failures) == 1
    assert "boom" in failures[0]["motivo"]


def test_gestor_callback_recebe_escolas_na_ordem(monkeypatch):
    _preparar_gestor(monkeypatch)
    gravadas = []

    outputs, failures = gestor_scraper.run_scraping(
        _BrowserFalso(), "l", "s", ESCOLAS,
        on_school_done=lambda escola, dados: gravadas.append(escola["codigo_inep"]),
    )

    assert gravadas == ["111", "222"]
    assert [e["codigo_inep"] for e, _ in outputs] == ["111", "222"]
    assert failures == []


def test_gestor_falha_do_callback_vira_nao_coletada(monkeypatch):
    _preparar_gestor(monkeypatch)

    def _boom(escola, dados):
        raise RuntimeError("boom")

    outputs, failures = gestor_scraper.run_scraping(
        _BrowserFalso(), "l", "s", ESCOLAS[:1], on_school_done=_boom,
    )

    assert outputs == []
    assert len(failures) == 1
    assert "boom" in failures[0]["motivo"]


def test_relatorios_callback_recebe_escolas_na_ordem(monkeypatch):
    _preparar_relatorios(monkeypatch)
    gravadas = []

    outputs, failures = report_scraper.run_report_scraping(
        _BrowserFalso(), "l", "s", ESCOLAS, "https://exemplo/rel",
        on_school_done=lambda escola, dados: gravadas.append(escola["codigo_inep"]),
    )

    assert gravadas == ["111", "222"]
    assert [e["codigo_inep"] for e, _ in outputs] == ["111", "222"]
    assert failures == []


def test_relatorios_falha_do_callback_vira_nao_coletada(monkeypatch):
    _preparar_relatorios(monkeypatch)

    def _boom(escola, dados):
        raise RuntimeError("boom")

    outputs, failures = report_scraper.run_report_scraping(
        _BrowserFalso(), "l", "s", ESCOLAS[:1], "https://exemplo/rel", on_school_done=_boom,
    )

    assert outputs == []
    assert len(failures) == 1
    assert "boom" in failures[0]["motivo"]


def test_recibos_callback_recebe_escolas_na_ordem(monkeypatch):
    _preparar_recibos(monkeypatch)
    gravadas = []

    outputs, failures = receipt_scraper.run_receipt_scraping(
        _BrowserFalso(), "l", "s", ESCOLAS, "https://exemplo/rec",
        on_school_done=lambda escola, dados: gravadas.append(escola["codigo_inep"]),
    )

    assert gravadas == ["111", "222"]
    assert [e["codigo_inep"] for e, _ in outputs] == ["111", "222"]
    assert failures == []


def test_recibos_falha_do_callback_vira_nao_coletada(monkeypatch):
    _preparar_recibos(monkeypatch)

    def _boom(escola, dados):
        raise RuntimeError("boom")

    outputs, failures = receipt_scraper.run_receipt_scraping(
        _BrowserFalso(), "l", "s", ESCOLAS[:1], "https://exemplo/rec", on_school_done=_boom,
    )

    assert outputs == []
    assert len(failures) == 1
    assert "boom" in failures[0]["motivo"]


# ── frontends: wiring do callback (sem loop pós-coleta duplicando) ─────────


class _ChromiumFalso:
    def launch(self, headless=True):
        return _BrowserFalso()


class _PlaywrightFalso:
    def __init__(self):
        self.chromium = _ChromiumFalso()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _sync_playwright_falso():
    return _PlaywrightFalso()


SHEET_CAD = next(iter(cad_modelo.load_model()))


def test_worker_cadastros_grava_uma_unica_vez(monkeypatch, tmp_path):
    escola = ESCOLAS[0]
    dados = {SHEET_CAD: {c: "" for c in cad_modelo.load_model()[SHEET_CAD]}}
    dados[SHEET_CAD]["Código do Inep"] = escola["codigo_inep"]

    def _run_falso(browser, login, senha, escolas, on_progress=None, stop_check=None,
                   on_school_done=None):
        on_school_done(escola, dados)
        return [(escola, dados)], []

    monkeypatch.setattr("playwright.sync_api.sync_playwright", _sync_playwright_falso)
    monkeypatch.setattr(cad_scraper, "run_scraping", _run_falso)

    shared: dict = {}
    cad_frontend._scrape_worker(
        "l", "s", [escola], threading.Event(), threading.Lock(), shared, tmp_path
    )

    assert shared["done"] is True
    assert shared.get("error") is None
    csv_path = tmp_path / f"{cad_exporter._safe_sheet_title(SHEET_CAD)}.csv"
    linhas = csv_path.read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 2  # cabeçalho + exatamente 1 escola (sem duplicação)
    assert "111" in linhas[1]


def test_worker_gestor_grava_uma_unica_vez(monkeypatch, tmp_path):
    escola = ESCOLAS[0]
    sheet = ges_modelo.GESTOR_SHEET
    dados = {sheet: {c: "" for c in ges_modelo.load_model()[sheet]}}
    dados[sheet]["Código do Inep"] = escola["codigo_inep"]

    def _run_falso(browser, login, senha, escolas, on_progress=None, stop_check=None,
                   on_school_done=None):
        on_school_done(escola, dados)
        return [(escola, dados)], []

    monkeypatch.setattr("playwright.sync_api.sync_playwright", _sync_playwright_falso)
    monkeypatch.setattr(gestor_scraper, "run_scraping", _run_falso)

    shared: dict = {}
    ges_frontend._scrape_worker(
        "l", "s", [escola], threading.Event(), threading.Lock(), shared, tmp_path
    )

    assert shared["done"] is True
    assert shared.get("error") is None
    csv_path = tmp_path / ges_exporter._sheet_file(sheet)
    linhas = csv_path.read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 2
    assert "111" in linhas[1]


def test_worker_relatorios_grava_uma_unica_vez(monkeypatch, tmp_path):
    escola = ESCOLAS[0]
    data = b"a;b\n1;2"

    def _run_falso(browser, login, senha, escolas, report_url, on_progress=None,
                   stop_check=None, on_school_done=None):
        on_school_done(escola, data)
        return [(escola, data)], []

    monkeypatch.setattr("playwright.sync_api.sync_playwright", _sync_playwright_falso)
    monkeypatch.setattr(report_scraper, "run_report_scraping", _run_falso)

    shared: dict = {}
    rel_frontend._scrape_worker(
        {"url": "https://exemplo/rel"}, "l", "s", [escola],
        threading.Event(), threading.Lock(), shared, tmp_path,
    )

    assert shared["done"] is True
    assert shared.get("error") is None
    csvs = sorted(p.name for p in tmp_path.glob("*.csv"))
    assert csvs == ["111_Escola Um.csv"]  # 1 arquivo → sem gravação duplicada
    assert (tmp_path / "111_Escola Um.csv").read_bytes() == data


def test_worker_recibos_grava_uma_unica_vez(monkeypatch, tmp_path):
    escola = ESCOLAS[0]
    data = b"%PDF-1.4\n%%EOF"

    def _run_falso(browser, login, senha, escolas, receipt_url, on_progress=None,
                   stop_check=None, on_school_done=None):
        on_school_done(escola, data)
        return [(escola, data)], []

    monkeypatch.setattr("playwright.sync_api.sync_playwright", _sync_playwright_falso)
    monkeypatch.setattr(receipt_scraper, "run_receipt_scraping", _run_falso)

    shared: dict = {}
    rec_frontend._scrape_worker(
        {"url": "https://exemplo/rec"}, "l", "s", [escola],
        threading.Event(), threading.Lock(), shared, tmp_path,
    )

    assert shared["done"] is True
    assert shared.get("error") is None
    pdfs = sorted(p.name for p in tmp_path.glob("*.pdf"))
    assert pdfs == ["111_Escola Um.pdf"]
    assert (tmp_path / "111_Escola Um.pdf").read_bytes() == data
