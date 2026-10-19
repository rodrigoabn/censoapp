"""Testes dos componentes comuns de UI dos coletores (`apps/common/ui.py`).

Cobre: `status_color` parametrizado pela tupla de cada app, `escapar` e
`linha_monitor` (mesmos casos pinados pelos monitores dos apps), `init_state`
idempotente (setdefault das 8 chaves) e a guarda de Chromium
(`chromium_already_installed`) — que evita reinstalar o navegador a cada
processo quando ele já está no cache do Playwright. Também trava os nomes
históricos do frontend do Relatórios (wrappers da T5).
"""

from __future__ import annotations

import types

from apps.common import ui


class _SubprocessFalso:
    """Fake de `subprocess.run`: registra chamadas e devolve um stdout fixo."""

    def __init__(self, stdout: str = "", erro: Exception | None = None):
        self.stdout = stdout
        self.erro = erro
        self.chamadas: list[tuple] = []

    def run(self, *args, **kwargs):
        self.chamadas.append((args, kwargs))
        if self.erro is not None:
            raise self.erro
        return types.SimpleNamespace(stdout=self.stdout, returncode=0)


def _subprocess_falso(monkeypatch, stdout: str = "") -> _SubprocessFalso:
    falso = _SubprocessFalso(stdout=stdout)
    monkeypatch.setattr(ui.subprocess, "run", falso.run)
    return falso


# ── status_color ────────────────────────────────────────────────────────────


def test_status_color_com_tupla_propria_do_app():
    indisponiveis = ("Recibo de fechamento indisponível.",)
    assert ui.status_color("concluído", indisponiveis) == "#22c55e"
    assert ui.status_color("Recibo de fechamento indisponível.", indisponiveis) == "#ef4444"
    assert ui.status_color("Relatório inexistente.", indisponiveis) == "#b2b5be"


def test_status_color_erro_e_falha_de_login_sao_vermelhos():
    assert ui.status_color("erro: escola não encontrada") == "#ef4444"
    assert ui.status_color("erro: sessão expirada — boom") == "#ef4444"
    assert ui.status_color("Falha no login") == "#ef4444"


def test_status_color_neutro():
    assert ui.status_color("Coletando dados ...") == "#b2b5be"
    assert ui.status_color("escola não encontrada") == "#b2b5be"


# ── escapar / linha_monitor ─────────────────────────────────────────────────


def test_escapar_protege_html():
    assert ui.escapar('<b>"x" & Cia</b>') == "&lt;b&gt;&quot;x&quot; &amp; Cia&lt;/b&gt;"


def test_linha_monitor_escapa_html():
    linha = ui.linha_monitor("Escola <b>X</b> & Cia", "#b2b5be")
    assert linha == "<span style='color:#b2b5be'>Escola &lt;b&gt;X&lt;/b&gt; &amp; Cia</span>"
    linha2 = ui.linha_monitor('Escola "Y" <script>', "#6e6e6e")
    assert linha2 == "<span style='color:#6e6e6e'>Escola &quot;Y&quot; &lt;script&gt;</span>"


# ── init_state ──────────────────────────────────────────────────────────────


class _StFalso:
    def __init__(self):
        self.session_state: dict = {}


def test_init_state_cria_as_oito_chaves():
    st_falso = _StFalso()
    ui.init_state("p_", st=st_falso)
    assert st_falso.session_state == {
        "p_running": False,
        "p_stop": None,
        "p_lock": None,
        "p_shared": None,
        "p_thread": None,
        "p_finalized": False,
        "p_zip": None,
        "p_pending": None,
    }


def test_init_state_nao_sobrescreve_valores_existentes():
    st_falso = _StFalso()
    st_falso.session_state["p_running"] = True
    st_falso.session_state["p_zip"] = ("bytes", "arquivo.zip")
    ui.init_state("p_", st=st_falso)
    assert st_falso.session_state["p_running"] is True
    assert st_falso.session_state["p_zip"] == ("bytes", "arquivo.zip")
    assert len(st_falso.session_state) == 8


# ── guarda do Chromium ──────────────────────────────────────────────────────


def test_chromium_already_installed_layout_novo(monkeypatch, tmp_path):
    chrome = tmp_path / "chrome-linux64" / "chrome"
    chrome.parent.mkdir(parents=True)
    chrome.write_text("#!/bin/sh\n", encoding="utf-8")

    falso = _subprocess_falso(monkeypatch, f"browser: chromium\nInstall location: {tmp_path}\n")
    assert ui.chromium_already_installed() is True

    comando = falso.chamadas[0][0][0]
    assert comando[1:] == ["-m", "playwright", "install", "--dry-run", "chromium"]


def test_chromium_already_installed_layout_antigo(monkeypatch, tmp_path):
    chrome = tmp_path / "chrome-linux" / "chrome"
    chrome.parent.mkdir(parents=True)
    chrome.write_text("#!/bin/sh\n", encoding="utf-8")
    _subprocess_falso(monkeypatch, f"Install location: {tmp_path}\n")
    assert ui.chromium_already_installed() is True


def test_chromium_already_installed_sem_chrome_na_pasta(monkeypatch, tmp_path):
    _subprocess_falso(monkeypatch, f"Install location: {tmp_path}\n")
    assert ui.chromium_already_installed() is False


def test_chromium_already_installed_sem_install_location(monkeypatch):
    _subprocess_falso(monkeypatch, "nada por aqui\n")
    assert ui.chromium_already_installed() is False


def test_chromium_already_installed_dry_run_falha(monkeypatch):
    falso = _SubprocessFalso(erro=RuntimeError("playwright ausente"))
    monkeypatch.setattr(ui.subprocess, "run", falso.run)
    assert ui.chromium_already_installed() is False


# ── nomes históricos e amarrações do frontend do Relatórios ────────────────


def test_rel_frontend_mantem_os_nomes_historicos():
    from apps.coleta_relatorios.src import frontend as rel_frontend

    for nome in (
        "_ensure_chromium",
        "_chromium_already_installed",
        "_SUBMIT_CSS",
        "_init_state",
        "_escapar",
        "_linha_monitor",
        "_status_color",
        "_scrape_worker",
        "_start_scraping",
        "_monitor",
        "_finalize",
        "render_report_frontend",
    ):
        assert hasattr(rel_frontend, nome), nome

    assert rel_frontend._SUBMIT_CSS is ui.SUBMIT_CSS


def test_rel_frontend_status_color_usa_a_tupla_propria():
    from apps.coleta_relatorios.src import frontend as rel_frontend

    assert rel_frontend._status_color("Relatório inexistente.") == "#ef4444"
    assert rel_frontend._status_color("Preenchimento não iniciado.") == "#ef4444"
    assert rel_frontend._status_color("concluído") == "#22c55e"
    assert rel_frontend._status_color("Recibo de fechamento indisponível.") == "#b2b5be"


def test_rel_frontend_escapar_e_linha_monitor_delegam_ao_comum():
    from apps.coleta_relatorios.src import frontend as rel_frontend

    assert rel_frontend._escapar("<x>") == ui.escapar("<x>")
    assert rel_frontend._linha_monitor("x & y", "#000") == ui.linha_monitor("x & y", "#000")
