"""Relatórios/Recibos: falha de login total e sessão expirada durante o download."""

from __future__ import annotations

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from apps.coleta_recibos_fechamento.src import receipt_scraper
from apps.coleta_relatorios.src import report_scraper

ESCOLAS = [{"codigo_inep": "111", "nome_unidade": "Escola Um"}]


class _LocatorFalso:
    @property
    def first(self):
        return self

    def count(self):
        return 0

    def is_visible(self):
        return False


class _BotaoFalso:
    @property
    def first(self):
        return self

    def click(self, *a, **k):
        raise PlaywrightTimeoutError("timeout")


class _PaginaFalsa:
    def goto(self, *a, **k):
        return None

    def wait_for_selector(self, *a, **k):
        return None

    def wait_for_timeout(self, *a, **k):
        return None

    def wait_for_load_state(self, *a, **k):
        return None

    def locator(self, *a, **k):
        return _LocatorFalso()

    def get_by_role(self, *a, **k):
        return _BotaoFalso()

    def close(self):
        return None


class _ContextoFalso:
    def new_page(self):
        return _PaginaFalsa()

    def clear_cookies(self):
        return None

    def close(self):
        return None


class _BrowserFalso:
    def new_context(self, **kwargs):
        return _ContextoFalso()


@pytest.fixture(autouse=True)
def _sem_espera(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)
    monkeypatch.setattr(report_scraper, "_wait_loader", lambda *a, **k: None)
    monkeypatch.setattr(receipt_scraper, "_wait_loader", lambda *a, **k: None)


def test_login_falho_vira_falhas_em_relatorios(monkeypatch):
    def _falha(*a, **k):
        raise report_scraper.LoginFalhou()

    monkeypatch.setattr(report_scraper, "_login_and_read", _falha)
    outputs, failures = report_scraper.run_report_scraping(
        _BrowserFalso(), "l", "s", ESCOLAS, "https://exemplo/relatorio"
    )
    assert outputs == []
    assert failures == [
        {"codigo_inep": "111", "nome_unidade": "Escola Um", "motivo": "Falha no login"}
    ]


def test_login_falho_vira_falhas_em_recibos(monkeypatch):
    def _falha(*a, **k):
        raise receipt_scraper.LoginFalhou()

    monkeypatch.setattr(receipt_scraper, "_login_and_read", _falha)
    outputs, failures = receipt_scraper.run_receipt_scraping(
        _BrowserFalso(), "l", "s", ESCOLAS, "https://exemplo/fechamento"
    )
    assert outputs == []
    assert failures == [
        {"codigo_inep": "111", "nome_unidade": "Escola Um", "motivo": "Falha no login"}
    ]


def test_download_de_relatorio_com_sessao_expirada_levanta_sessao_expirada(monkeypatch):
    monkeypatch.setattr(report_scraper, "_session_expirada", lambda page: True)
    with pytest.raises(report_scraper.SessaoExpirada):
        report_scraper._download_report_csv(_PaginaFalsa(), "https://exemplo/relatorio")


def test_download_de_recibo_com_sessao_expirada_levanta_sessao_expirada(monkeypatch):
    monkeypatch.setattr(receipt_scraper, "_session_expirada", lambda page: True)
    with pytest.raises(receipt_scraper.SessaoExpirada):
        receipt_scraper._download_receipt_pdf(
            _ContextoFalso(), _PaginaFalsa(), "https://exemplo/fechamento"
        )


def test_relatorio_sem_preenchimento_segue_levantando_preenchimento_nao_iniciado(monkeypatch):
    monkeypatch.setattr(report_scraper, "_session_expirada", lambda page: False)
    with pytest.raises(report_scraper.PreenchimentoNaoIniciado):
        report_scraper._download_report_csv(_PaginaFalsa(), "https://exemplo/relatorio")


def test_recibo_indisponivel_segue_quando_sessao_ok(monkeypatch):
    monkeypatch.setattr(receipt_scraper, "_session_expirada", lambda page: False)
    with pytest.raises(receipt_scraper.ReciboIndisponivel):
        receipt_scraper._download_receipt_pdf(
            _ContextoFalso(), _PaginaFalsa(), "https://exemplo/fechamento"
        )
