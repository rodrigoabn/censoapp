"""Termo de sigilo: sonda curta (1,5 s) e espera pela saída do diálogo.

Antes, a função esperava 8 s pelo diálogo (mesmo quando ele não vinha, que é o
caso comum) e dormia 3 s fixos após o aceite. Agora a sonda é curta e a espera
final observa o diálogo sair do DOM, com fallback.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from apps.coleta_gestor.src import gestor_scraper
from apps.coleta_recibos_fechamento.src import receipt_scraper
from apps.coleta_relatorios.src import report_scraper
from src import scraper as cad_scraper

MODULOS = [cad_scraper, gestor_scraper, report_scraper, receipt_scraper]
IDS = ["cadastros", "gestor", "relatorios", "recibos"]


class _LocatorFalso:
    def __init__(self, pagina, seletor):
        self._pagina = pagina
        self._seletor = seletor

    @property
    def first(self):
        return self

    def count(self):
        return 1

    def is_disabled(self):
        return False

    def is_enabled(self):
        return True

    def check(self, force=False):
        self._pagina.chamadas.append(("check", self._seletor, force))

    def click(self):
        self._pagina.chamadas.append(("click", self._seletor))


class _PaginaFalsa:
    def __init__(self, *, presente: bool):
        self.presente = presente
        self.chamadas: list[tuple] = []

    def wait_for_selector(self, seletor, timeout=None, state=None):
        self.chamadas.append(("wait_for_selector", seletor, timeout, state))
        if state == "detached":
            return None
        if not self.presente:
            raise PlaywrightTimeoutError(f"Timeout {timeout}ms: {seletor}")
        return object()

    def evaluate(self, script):
        self.chamadas.append(("evaluate", script))

    def wait_for_timeout(self, ms):
        self.chamadas.append(("wait_for_timeout", ms))

    def locator(self, seletor):
        self.chamadas.append(("locator", seletor))
        return _LocatorFalso(self, seletor)


def _executar(modulo, *, presente: bool) -> list[tuple]:
    pagina = _PaginaFalsa(presente=presente)
    modulo._accept_sigilo_if_present(pagina)
    return pagina.chamadas


@pytest.mark.parametrize("modulo", MODULOS, ids=IDS)
def test_sigilo_ausente_sonda_curta_e_sem_sleep_fixo(modulo):
    chamadas = _executar(modulo, presente=False)

    sondas = [c for c in chamadas if c[0] == "wait_for_selector" and c[3] is None]
    assert sondas, "a sonda pelo diálogo deveria ter sido chamada"
    assert sondas[0][2] == 1500
    assert ("wait_for_timeout", 3000) not in chamadas


@pytest.mark.parametrize("modulo", MODULOS, ids=IDS)
def test_sigilo_presente_marca_aceite_e_espera_saida(modulo):
    chamadas = _executar(modulo, presente=True)

    assert any(c[0] == "check" and c[2] is True for c in chamadas)
    assert any(c[0] == "click" for c in chamadas)

    saidas = [c for c in chamadas if c[0] == "wait_for_selector" and c[3] == "detached"]
    assert saidas, "espera pela saída do diálogo (state='detached')"
    assert saidas[0][2] == 5000
    assert ("wait_for_timeout", 3000) not in chamadas
