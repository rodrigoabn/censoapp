"""Testes dos componentes comuns das coletas (`apps/common/ui.py`).

Cobre: `escapar` e `linha_monitor` (texto sempre escapado), `status_color` dos
estados, o progresso compartilhado com a thread de coleta, o relógio da rodada
(duração, marcação de início/término e conteúdo digital) e a guarda de
Chromium (`chromium_already_installed`) — que evita reinstalar o navegador a
cada processo quando ele já está no cache do Playwright.
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
    html = ui._relogio_resumo_conteudo_html(inicio, fim)

    assert "Início da coleta" in html
    assert "Término da coleta" in html
    assert "Tempo de execução" in html
    assert "relogio-digital" in html
    assert "20/10/2026" in html
    assert "19:57:03" in html
    assert "20/10/2026" in html
    assert "20:01:20" in html
    assert "00:04:17" in html


def test_relogio_digital_mostra_tempo_em_andamento():
    from datetime import datetime

    inicio = datetime(2026, 10, 20, 19, 57, 3)
    html = ui._relogio_andamento_conteudo_html(83.0, inicio)

    assert "Tempo em andamento" in html
    assert "relogio-andamento" in html
    assert "relogio-digital" in html
    assert "00:01:23" in html
    assert "relogio-inicio" in html
    assert "20/10/2026" in html
    assert "19:57:03" in html


# ── barra de progresso das escolas ──────────────────────────────────────────


def test_progresso_escolas_mostra_conta_e_percentual():
    html = ui._progresso_escolas_html(coletadas=22, processadas=22, total=220)

    assert "22/220" in html
    assert "10% concluído" in html
    assert "aria-valuenow='10'" in html
    assert "width:10%" in html
    assert "relogio-progresso-barra" in html


def test_progresso_escolas_com_falhas_avanca_por_processadas():
    """A barra segue o trabalho processado; o rótulo diz o que foi coletado."""
    html = ui._progresso_escolas_html(coletadas=22, processadas=25, total=220)

    assert "22/220" in html
    assert "11% concluído" in html
    assert "3 não coletadas" in html
    assert "aria-valuenow='11'" in html


def test_progresso_escolas_uma_nao_coletada_no_singular():
    html = ui._progresso_escolas_html(coletadas=21, processadas=22, total=220)

    assert "1 não coletada" in html
    assert "não coletadas" not in html


def test_progresso_escolas_total_zero_nao_divide_por_zero():
    html = ui._progresso_escolas_html(coletadas=0, processadas=0, total=0)

    assert "0/0" in html
    assert "0% concluído" in html
    assert "aria-valuenow='0'" in html
    assert "width:0%" in html


def test_progresso_escolas_nao_passa_de_cem_por_cento():
    """Contagem acima do total (não deveria acontecer) é presa ao total."""
    html = ui._progresso_escolas_html(coletadas=230, processadas=230, total=220)

    assert "220/220" in html
    assert "100% concluído" in html
    assert "aria-valuenow='100'" in html


def test_progresso_escolas_nao_mostra_cem_antes_da_ultima():
    """219/220 = 99,5% vira 99: a barra só fecha com a última escola."""
    html = ui._progresso_escolas_html(coletadas=219, processadas=219, total=220)

    assert "99% concluído" in html
    assert "aria-valuenow='99'" in html


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


# ── worker_base: falha de login ─────────────────────────────────────────────


class _BrowserWorkerFalso:
    def __init__(self):
        self.fechado = False

    def close(self):
        self.fechado = True


class _ChromiumWorkerFalso:
    def __init__(self):
        self.browser = _BrowserWorkerFalso()

    def launch(self, **kwargs):
        return self.browser


class _PlaywrightWorkerFalso:
    def __init__(self):
        self.chromium = _ChromiumWorkerFalso()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_worker_base_registra_falha_de_login(monkeypatch):
    """O worker precisa publicar o motivo e a marca de login para a rodada."""
    from apps.common.session import LoginFalhou

    def chamar_coleta(*a, **k):
        raise LoginFalhou("Nome de usuário ou senha inválida.")

    falso = _PlaywrightWorkerFalso()
    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: falso)

    shared = {"error": None, "login_falhou": False, "login_mensagem": None}
    ui.worker_base(
        "123",
        "senha",
        [{"codigo_inep": "1", "nome_unidade": "Escola"}],
        threading.Event(),
        threading.Lock(),
        shared,
        chamar_coleta=chamar_coleta,
        gravar=lambda *a: None,
    )

    assert shared["error"] == "Nome de usuário ou senha inválida."
    assert shared["login_falhou"] is True
    assert shared["login_mensagem"] == "Nome de usuário ou senha inválida."
    assert shared["done"] is True
    assert falso.chromium.browser.fechado is True
