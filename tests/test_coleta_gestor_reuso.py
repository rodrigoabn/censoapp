"""Gestor: Fase B reaproveita a lista de vínculos carregada pela Fase A.

Com `reload=False`, `_scrape_gestor_edit_form` tenta usar o ícone de edição já
presente na página (a Fase A acabou de deixar a lista aberta); só navega para
`/gestor/pesquisar` de novo se o ícone não estiver disponível — evita refazer
a busca na rota de cada escola.
"""

from __future__ import annotations

import pytest

from apps.coleta_gestor.src import gestor_scraper

ICONE_PRIMEIRO = "mat-icon[mattooltip*='dados cadastrais']"


class _LocatorFalso:
    def __init__(self, pagina, seletor):
        self._pagina = pagina
        self._seletor = seletor

    @property
    def first(self):
        return self

    def count(self):
        if self._seletor == ICONE_PRIMEIRO and self._pagina.icone_presente:
            return 1
        return 0

    def click(self, timeout=None, force=False):
        self._pagina.cliques.append(self._seletor)

    def is_visible(self):
        return False


class _PaginaFalsa:
    def __init__(self, *, icone_presente: bool):
        self.icone_presente = icone_presente
        self.cliques: list[str] = []

    def locator(self, seletor):
        return _LocatorFalso(self, seletor)

    def goto(self, *a, **k):
        pass

    def wait_for_selector(self, seletor, timeout=None, state=None):
        return object()

    def wait_for_timeout(self, ms):
        pass

    def evaluate(self, script):
        return []


@pytest.fixture(autouse=True)
def _neutralizar_pos_click(monkeypatch):
    monkeypatch.setattr(gestor_scraper, "_wait_loader", lambda *a, **k: None)
    monkeypatch.setattr(gestor_scraper, "_is_escola_fechada", lambda page: False)
    monkeypatch.setattr(gestor_scraper, "_accept_sigilo_if_present", lambda *a, **k: None)
    monkeypatch.setattr(gestor_scraper, "_wait_content_ready", lambda *a, **k: True)
    monkeypatch.setattr(gestor_scraper, "_extract_with_retry", lambda *a, **k: [])
    monkeypatch.setattr(gestor_scraper, "_fechar_ou_cancelar_gestor", lambda *a, **k: None)


def test_reload_false_reaproveita_icone_sem_navegar(monkeypatch):
    def _nao_deveria_navegar(page):
        raise AssertionError("_abrir_pesquisa_gestor não deveria ser chamado")

    monkeypatch.setattr(gestor_scraper, "_abrir_pesquisa_gestor", _nao_deveria_navegar)
    pagina = _PaginaFalsa(icone_presente=True)

    resultado = gestor_scraper._scrape_gestor_edit_form(
        pagina, "111", "Escola Um", reload=False
    )

    assert resultado == {}
    assert pagina.cliques == [ICONE_PRIMEIRO]


def test_reload_false_sem_icone_cai_no_fallback(monkeypatch):
    chamadas = []

    def _abrir(page):
        chamadas.append(1)
        return 0

    monkeypatch.setattr(gestor_scraper, "_abrir_pesquisa_gestor", _abrir)
    pagina = _PaginaFalsa(icone_presente=False)

    resultado = gestor_scraper._scrape_gestor_edit_form(
        pagina, "111", "Escola Um", reload=False
    )

    assert resultado == {}
    assert len(chamadas) == 1


def test_scrape_gestor_school_fase_b_sem_reload(monkeypatch):
    capturado = {}

    monkeypatch.setattr(gestor_scraper, "_open_school_ficha", lambda page, codigo: True)
    monkeypatch.setattr(gestor_scraper, "_scrape_gestor_vinculo", lambda *a, **k: {})

    def _edit_form_falso(page, codigo_inep, nome_unidade, **kwargs):
        capturado.update(kwargs)
        return {"Identificação": {"Código do Inep": codigo_inep}}

    monkeypatch.setattr(gestor_scraper, "_scrape_gestor_edit_form", _edit_form_falso)

    resultado = gestor_scraper.scrape_gestor_school(
        _PaginaFalsa(icone_presente=True), "111", "Escola Um"
    )

    assert capturado == {"reload": False}
    assert resultado is not None
    assert resultado["Identificação"]["Código do Inep"] == "111"
