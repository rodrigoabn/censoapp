"""Testes dos componentes comuns de UI dos coletores (`apps/common/ui.py`).

Cobre: `status_color` parametrizado pela tupla de cada app, `escapar` e
`linha_monitor` (mesmos casos pinados pelos monitores dos apps), `init_state`
idempotente (setdefault das 10 chaves), o relógio da coleta (duração, marcação
de início/término e o relógio digital do monitor) e a guarda de Chromium
(`chromium_already_installed`) — que evita reinstalar o navegador a cada
processo quando ele já está no cache do Playwright. Também trava os nomes
históricos dos frontends de Relatórios, Recibos, Cadastros e Gestor
(wrappers das T5–T7).
"""

from __future__ import annotations

import threading
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


def test_status_color_erro_sao_vermelhos():
    assert ui.status_color("erro: escola não encontrada") == "#ef4444"
    assert ui.status_color("erro: sessão expirada — boom") == "#ef4444"


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


def test_init_state_cria_as_dez_chaves():
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
        "p_inicio": None,
        "p_fim": None,
    }


def test_init_state_nao_sobrescreve_valores_existentes():
    st_falso = _StFalso()
    st_falso.session_state["p_running"] = True
    st_falso.session_state["p_zip"] = ("bytes", "arquivo.zip")
    ui.init_state("p_", st=st_falso)
    assert st_falso.session_state["p_running"] is True
    assert st_falso.session_state["p_zip"] == ("bytes", "arquivo.zip")
    assert len(st_falso.session_state) == 10


# ── progresso compartilhado com a thread de coleta ───────────────────────────


def test_registrar_progresso_marca_a_escola_atual():
    shared: dict = {}
    ui.registrar_progresso(
        shared, threading.Lock(), 1, 2, "111", "Escola Um", "Coletando dados ..."
    )
    assert shared["current"] == (1, 2, "Escola Um", "111")
    assert shared["total"] == 2
    assert shared["aviso"] is None


def test_registrar_progresso_avisa_a_nova_tentativa_e_limpa_a_escola_atual():
    shared = {"current": (1, 2, "Escola Um", "111")}
    ui.registrar_progresso(
        shared, threading.Lock(), 1, 2, "111", "Escola Um", "nova tentativa 2 de 5 (timeout)"
    )
    assert shared["aviso"] == ("111", "Escola Um", "nova tentativa 2 de 5 (timeout)")
    assert shared["current"] is None


def test_registrar_progresso_coleta_limpa_o_aviso():
    shared = {"aviso": ("111", "Escola Um", "nova tentativa 2 de 5 (timeout)")}
    ui.registrar_progresso(
        shared, threading.Lock(), 1, 2, "111", "Escola Um", "Coletando dados ..."
    )
    assert shared["aviso"] is None


def test_registrar_progresso_concluido_conta_e_vai_para_o_ultimo():
    shared = {"count": 1, "aviso": ("111", "Escola Um", "nova tentativa 2 de 5 (timeout)")}
    ui.registrar_progresso(shared, threading.Lock(), 1, 2, "111", "Escola Um", "concluído")
    assert shared["count"] == 2
    assert shared["last"] == (1, 2, "Escola Um", "111", "concluído")
    assert shared["current"] is None
    assert shared["aviso"] is None


# ── relógio da coleta ────────────────────────────────────────────────────────


def test_duracao_em_hh_mm_ss():
    assert ui._duracao(0) == "00:00:00"
    assert ui._duracao(9) == "00:00:09"
    assert ui._duracao(75) == "00:01:15"
    assert ui._duracao(3723) == "01:02:03"
    assert ui._duracao(-5) == "00:00:00"


def test_resumo_mostra_inicio_termino_e_execucao():
    from datetime import datetime

    inicio = datetime(2026, 10, 20, 19, 57, 3)
    fim = datetime(2026, 10, 20, 20, 1, 20)
    html = ui._relogio_resumo_html(inicio, fim)

    assert "Horário inicial" in html
    assert "Horário de término" in html
    assert "Tempo de execução" in html
    assert "20/10/2026 19:57:03" in html
    assert "20/10/2026 20:01:20" in html
    assert "00:04:17" in html


def test_relogio_digital_mostra_tempo_em_andamento():
    from datetime import datetime

    inicio = datetime(2026, 10, 20, 19, 57, 3)
    html = ui._relogio_andamento_html(83.0, inicio)

    assert "Tempo em andamento" in html
    assert "relogio-digital" in html
    assert "00:01:23" in html
    assert "20/10/2026 19:57:03" in html


def test_monitor_desenha_o_relogio_digital_durante_a_coleta():
    import re
    import threading
    from datetime import datetime, timedelta

    class _St:
        def __init__(self, ss):
            self.session_state = ss
            self.markdowns = []

        def markdown(self, body, **kwargs):
            self.markdowns.append(body)

        def button(self, label, **kwargs):
            return False

        def progress(self, valor):
            pass

        def warning(self, msg):
            pass

        def rerun(self):
            raise AssertionError("o monitor não pode abortar o script")

    ss = {
        "p_lock": threading.Lock(),
        "p_shared": {"current": None, "last": None, "count": 0, "total": 1, "done": False},
        "p_stop": threading.Event(),
        "p_inicio": datetime.now() - timedelta(seconds=90),
    }
    st_falso = _St(ss)
    ctx = ui.FrontendCtx(
        st=st_falso, zipper=None, textos=ui.TextosFrontend(),
        scrape_worker=None, monitor=None, finalize=None, start=None,
    )

    ui.monitor_base({"state_prefix": "p_"}, ctx=ctx)

    html = "\n".join(st_falso.markdowns)
    assert "relogio-digital" in html
    assert re.search(r"00:01:2\d|00:01:3\d", html), html


def test_monitor_nao_aborta_o_script():
    """O monitor redesenha por fragmento; abortar o script deixa restos da
    tela anterior na árvore de elementos do frontend."""
    import inspect

    fonte = inspect.getsource(ui.monitor_base)
    # só o "rerun" de conclusão (a coleta acabou) é permitido
    assert fonte.count("st.rerun()") == 1
    assert "time.sleep" not in fonte
    assert hasattr(ui, "_fragmento_monitor")


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


# ── Recibos: nomes históricos e amarrações ───────────────────────────────────


def test_rec_frontend_mantem_os_nomes_historicos():
    from apps.coleta_recibos_fechamento.src import frontend as rec_frontend

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
        "render_receipt_frontend",
    ):
        assert hasattr(rec_frontend, nome), nome

    assert rec_frontend._SUBMIT_CSS is ui.SUBMIT_CSS


def test_rec_frontend_status_color_usa_a_tupla_propria():
    from apps.coleta_recibos_fechamento.src import frontend as rec_frontend

    assert rec_frontend._status_color("Recibo de fechamento indisponível.") == "#ef4444"
    assert rec_frontend._status_color("concluído") == "#22c55e"
    assert rec_frontend._status_color("Relatório inexistente.") == "#b2b5be"
    assert rec_frontend._status_color("Preenchimento não iniciado.") == "#b2b5be"


def test_rec_frontend_escapar_e_linha_monitor_delegam_ao_comum():
    from apps.coleta_recibos_fechamento.src import frontend as rec_frontend

    assert rec_frontend._escapar("<x>") == ui.escapar("<x>")
    assert rec_frontend._linha_monitor("x & y", "#000") == ui.linha_monitor("x & y", "#000")


# ── Cadastros: nomes históricos e amarrações ────────────────────────────────


def test_cad_frontend_mantem_os_nomes_historicos():
    from apps.coleta_cadastros_escolas.src import frontend as cad_frontend

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
        "render_frontend",
        # adaptadores config-first exigidos pelo FrontendCtx
        "_scrape_worker_com_config",
        "_monitor_com_config",
        "_finalize_com_config",
        "_start_com_config",
        "_ctx",
        "CONFIG",
        "_TEXTOS",
    ):
        assert hasattr(cad_frontend, nome), nome

    assert cad_frontend._SUBMIT_CSS is ui.SUBMIT_CSS


def test_cad_frontend_status_color_com_tupla_vazia():
    from apps.coleta_cadastros_escolas.src import frontend as cad_frontend

    assert cad_frontend._status_color("erro: escola não encontrada") == "#ef4444"
    assert cad_frontend._status_color("concluído") == "#22c55e"
    assert cad_frontend._status_color("escola não encontrada") == "#b2b5be"
    assert cad_frontend._status_color("Recibo de fechamento indisponível.") == "#b2b5be"


def test_cad_frontend_escapar_e_linha_monitor_delegam_ao_comum():
    from apps.coleta_cadastros_escolas.src import frontend as cad_frontend

    assert cad_frontend._escapar("<x>") == ui.escapar("<x>")
    assert cad_frontend._linha_monitor("x & y", "#000") == ui.linha_monitor("x & y", "#000")


# ── Gestor: nomes históricos e amarrações ───────────────────────────────────


def test_gestor_frontend_mantem_os_nomes_historicos():
    from apps.coleta_gestor.src import frontend as ges_frontend

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
        "render_gestor_frontend",
        # adaptadores config-first exigidos pelo FrontendCtx
        "_scrape_worker_com_config",
        "_monitor_com_config",
        "_finalize_com_config",
        "_start_com_config",
        "_ctx",
        "CONFIG",
        "_TEXTOS",
    ):
        assert hasattr(ges_frontend, nome), nome

    assert ges_frontend._SUBMIT_CSS is ui.SUBMIT_CSS


def test_gestor_frontend_status_color_com_tupla_vazia():
    from apps.coleta_gestor.src import frontend as ges_frontend

    assert ges_frontend._status_color("erro: escola não encontrada") == "#ef4444"
    assert ges_frontend._status_color("concluído") == "#22c55e"
    assert ges_frontend._status_color("escola não encontrada") == "#b2b5be"
    assert ges_frontend._status_color("Relatório inexistente.") == "#b2b5be"


def test_gestor_frontend_escapar_e_linha_monitor_delegam_ao_comum():
    from apps.coleta_gestor.src import frontend as ges_frontend

    assert ges_frontend._escapar("<x>") == ui.escapar("<x>")
    assert ges_frontend._linha_monitor("x & y", "#000") == ui.linha_monitor("x & y", "#000")
