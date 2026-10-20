"""Fluxo do gestor: vínculo via 'editing' no modal e abas do cadastro.

Regressão do defeito em que a Fase A exigia mais de um ícone 'visibility'
(inexistente no portal), deixava o modal aberto e a Fase B clicava num ícone
coberto pelo backdrop — resultando em 0 campos em todas as escolas.
"""

from __future__ import annotations

from apps.coleta_gestor.src import gestor_scraper, modelo

CAMPOS_VINCULO = [
    {"label": "1 - Cargo", "value": "Diretor"},
    {"label": "2 - Critério de acesso ao cargo/função", "value": "Indicação"},
    {"label": "3 - Situação Funcional/Regime de contratação/Tipo de vínculo", "value": "Efetivo"},
    {"label": "Email principal", "value": "gestor@example.com"},
]

CAMPOS_BUSCA = [
    {"label": "CPF", "value": ""},
    {"label": "Nome completo", "value": ""},
]


class _TecladoFalso:
    def __init__(self, pagina):
        self._pagina = pagina

    def press(self, tecla):
        if tecla == "Escape":
            self._pagina.escape += 1
            self._pagina.dialogos = max(0, self._pagina.dialogos - 1)


class _LocatorFalso:
    def __init__(self, pagina, seletor, contexto="page"):
        self._pagina = pagina
        self._seletor = seletor
        self._contexto = contexto

    @property
    def first(self):
        return self

    @property
    def last(self):
        return self

    def locator(self, seletor):
        return _LocatorFalso(self._pagina, seletor, contexto="dialog")

    def count(self):
        if self._contexto == "dialog":
            return 1 if "editing" in self._seletor and not self._pagina.sem_editing else 0
        if self._seletor == "mat-icon:has-text('list')":
            return 1
        if self._seletor == "mat-dialog-container":
            return self._pagina.dialogos
        if self._seletor == "icone-edicao":
            return self._pagina.icone_edicao_presente
        return 0

    def click(self, timeout=None, force=False):
        self._pagina.cliques.append(f"{self._contexto}:{self._seletor}")

    def is_visible(self):
        return False

    def inner_text(self):
        return ""


class _PaginaFalsa:
    def __init__(
        self,
        *,
        sem_editing: bool = False,
        dialogos: int = 0,
        icone_edicao_presente: bool = True,
    ):
        self.sem_editing = sem_editing
        self.dialogos = dialogos
        self.icone_edicao_presente = icone_edicao_presente
        self.cliques: list[str] = []
        self.esperas: list[str] = []
        self.avaliacoes: list[list[dict]] = []
        self.escape = 0
        self.keyboard = _TecladoFalso(self)

    def locator(self, seletor):
        return _LocatorFalso(self, seletor)

    def wait_for_selector(self, seletor, timeout=None, state=None):
        self.esperas.append(seletor)
        return object()

    def wait_for_timeout(self, ms):
        pass

    def evaluate(self, script):
        return self.avaliacoes.pop(0) if self.avaliacoes else []


def _neutralizar_fase_a(monkeypatch):
    monkeypatch.setattr(gestor_scraper, "_abrir_pesquisa_gestor", lambda page: 1)
    monkeypatch.setattr(gestor_scraper, "_wait_loader", lambda *a, **k: None)
    monkeypatch.setattr(gestor_scraper, "_is_escola_fechada", lambda page: True)
    monkeypatch.setattr(gestor_scraper, "_accept_sigilo_if_present", lambda *a, **k: None)


def _neutralizar_fase_b(monkeypatch):
    monkeypatch.setattr(gestor_scraper, "_abrir_pesquisa_gestor", lambda page: 1)
    monkeypatch.setattr(gestor_scraper, "_wait_loader", lambda *a, **k: None)
    monkeypatch.setattr(gestor_scraper, "_is_escola_fechada", lambda page: False)
    monkeypatch.setattr(gestor_scraper, "_accept_sigilo_if_present", lambda *a, **k: None)
    monkeypatch.setattr(gestor_scraper, "_wait_content_ready", lambda *a, **k: True)
    monkeypatch.setattr(gestor_scraper, "_extract_with_retry", lambda *a, **k: [])
    monkeypatch.setattr(gestor_scraper, "_fechar_ou_cancelar_gestor", lambda *a, **k: None)


def test_fase_a_abre_editing_do_modal_e_fecha(monkeypatch):
    """A Fase A usa o 'editing' da linha do modal e fecha os diálogos no fim."""
    pagina = _PaginaFalsa(dialogos=1)
    _neutralizar_fase_a(monkeypatch)
    monkeypatch.setattr(gestor_scraper, "_extract_vinculo", lambda page, cols: CAMPOS_VINCULO)

    def _fechar(page):
        pagina.cliques.append("fechou-dialogos")

    monkeypatch.setattr(gestor_scraper, "_fechar_todos_dialogos", _fechar)

    row = gestor_scraper._scrape_gestor_vinculo(pagina, "33008256", "CE 29 DE MAIO")
    cols = modelo.load_model()[modelo.GESTOR_SHEET]

    assert row[cols[2]] == "Diretor"
    assert row[cols[3]] == "Indicação"
    assert row[cols[4]] == "Efetivo"
    assert row[cols[5]] == "gestor@example.com"
    assert row["Código do Inep"] == "33008256"
    assert "dialog:mat-icon:has-text('editing')" in pagina.cliques
    assert "visibility" not in " ".join(pagina.cliques)
    assert pagina.cliques[-1] == "fechou-dialogos"


def test_fase_a_sem_editing_fecha_e_retorna_vazio(monkeypatch):
    """Sem o ícone 'editing' no modal, a Fase A não deixa o modal aberto."""
    pagina = _PaginaFalsa(dialogos=1, sem_editing=True)
    _neutralizar_fase_a(monkeypatch)

    def _fechar(page):
        pagina.cliques.append("fechou-dialogos")

    monkeypatch.setattr(gestor_scraper, "_fechar_todos_dialogos", _fechar)

    row = gestor_scraper._scrape_gestor_vinculo(pagina, "111", "Escola Um")

    assert row["Código do Inep"] == "111"
    assert all(v == "" for c, v in row.items() if c not in modelo.KEY_COLUMNS)
    assert "fechou-dialogos" in pagina.cliques


def test_extract_vinculo_ignora_filtros_da_busca():
    """A extração espera o formulário do vínculo, não os filtros da pesquisa."""
    pagina = _PaginaFalsa()
    pagina.avaliacoes = [CAMPOS_BUSCA, CAMPOS_VINCULO]
    cols = modelo.load_model()[modelo.GESTOR_SHEET]

    fields = gestor_scraper._extract_vinculo(pagina, cols, timeout=2000)

    assert fields == CAMPOS_VINCULO
    assert pagina.avaliacoes == []


def test_fase_b_espera_abas_do_cadastro(monkeypatch):
    """A Fase B espera 'li.tab-item'; 'mat-form-field' sozinho é a tela de busca."""
    pagina = _PaginaFalsa()
    _neutralizar_fase_b(monkeypatch)
    monkeypatch.setattr(
        gestor_scraper,
        "_buscar_icone_edicao",
        lambda page: _LocatorFalso(pagina, "icone-edicao"),
    )

    resultado = gestor_scraper._scrape_gestor_edit_form(
        pagina, "111", "Escola Um", reload=True
    )

    assert resultado == {}
    assert pagina.esperas == ["li.tab-item"]
    assert pagina.cliques == ["page:icone-edicao"]


def test_fechar_todos_dialogos_usa_escape_e_fecha(monkeypatch):
    """Fecha o diálogo com Escape e garante o fechamento do que restar."""
    pagina = _PaginaFalsa(dialogos=1)
    fechamentos: list[int] = []
    monkeypatch.setattr(
        gestor_scraper,
        "_fechar_ou_cancelar_gestor",
        lambda page: fechamentos.append(1),
    )

    gestor_scraper._fechar_todos_dialogos(pagina)

    assert pagina.escape == 1
    assert pagina.dialogos == 0
    assert fechamentos == [1]


def test_fechar_ou_cancelar_nunca_usa_salvar():
    """O fechamento do formulário nunca aciona o botão 'Salvar'."""
    seletores: list[str] = []

    class _PaginaSoSeletores:
        def locator(self, seletor):
            seletores.append(seletor)
            return _LocatorFalso(_PaginaFalsa(), seletor)

        def wait_for_timeout(self, ms):
            pass

    gestor_scraper._fechar_ou_cancelar_gestor(_PaginaSoSeletores())

    assert seletores
    assert all("Salvar" not in s for s in seletores)
    assert any("Cancelar" in s for s in seletores)
