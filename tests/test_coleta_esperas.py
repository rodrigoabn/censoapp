"""Espera da abertura de ficha/seleção de escola sem `networkidle`.

O portal mantém requisições abertas (polling), então `networkidle` estourava o
timeout de 10 s em toda escola. O portão passa a ser o seletor-união: o campo
de busca aparecer **ou** a tela de login (sessão expirada) — mantendo a
detecção de expiração rápida.
"""

from __future__ import annotations

from apps.coleta_recibos_fechamento.src import receipt_scraper
from apps.coleta_relatorios.src import report_scraper
from src import scraper as cad_scraper

UNIAO = "input#username, input[formcontrolname='codigoEscola']"


class _LocatorFalso:
    @property
    def first(self):
        return self

    def count(self):
        return 0

    def is_visible(self):
        return False


class _PaginaFalsa:
    def __init__(self):
        self.chamadas: list[tuple] = []

    def goto(self, *a, **k):
        self.chamadas.append(("goto", a[0]))

    def wait_for_load_state(self, *a, **k):
        self.chamadas.append(("wait_for_load_state", a, k))

    def wait_for_selector(self, seletor, timeout=None, state=None):
        self.chamadas.append(("wait_for_selector", seletor, timeout, state))
        return object()

    def wait_for_timeout(self, ms):
        self.chamadas.append(("wait_for_timeout", ms))

    def locator(self, seletor):
        self.chamadas.append(("locator", seletor))
        return _LocatorFalso()

    def fill(self, seletor, valor):
        self.chamadas.append(("fill", seletor, valor))

    def evaluate(self, script):
        self.chamadas.append(("evaluate",))


def _assertar_portao_por_seletor(pagina) -> None:
    assert not [c for c in pagina.chamadas if c[0] == "wait_for_load_state"]
    uniao = [c for c in pagina.chamadas if c[0] == "wait_for_selector" and c[1] == UNIAO]
    assert uniao, "espera pelo seletor-união (campo de busca ou login)"
    assert uniao[0][2] == 15000


def test_cadastros_abre_ficha_sem_networkidle():
    pagina = _PaginaFalsa()

    resultado = cad_scraper._open_school_ficha(pagina, "111")

    assert resultado is False  # link.count()==0 → não encontrada
    _assertar_portao_por_seletor(pagina)


def test_relatorios_seleciona_escola_sem_networkidle():
    pagina = _PaginaFalsa()

    resultado = report_scraper._select_school(pagina, "111")

    assert resultado is False
    _assertar_portao_por_seletor(pagina)


def test_recibos_seleciona_escola_sem_networkidle():
    pagina = _PaginaFalsa()

    resultado = receipt_scraper._select_school(pagina, "111")

    assert resultado is False
    _assertar_portao_por_seletor(pagina)
