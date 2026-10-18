"""Sinaliza eventos de parada ao trocar de página no HUB."""

from __future__ import annotations

import threading

from hub_sessao import liberar_execucoes


def test_liberar_execucoes_sinaliza_eventos_de_parada():
    ev_a, ev_b = threading.Event(), threading.Event()
    estado = {"ws_stop": ev_a, "cg_stop": ev_b, "ws_running": True, "nav_page": "x"}
    assert liberar_execucoes(estado) == 2
    assert ev_a.is_set() and ev_b.is_set()
    assert estado["ws_running"] is True and estado["nav_page"] == "x"


def test_liberar_execucoes_sem_eventos_retorna_zero():
    assert liberar_execucoes({"a": 1, "b": "texto"}) == 0


def test_liberar_execucoes_com_evento_ja_setado_e_inofensivo():
    ev = threading.Event()
    ev.set()
    assert liberar_execucoes({"stop": ev}) == 1
    assert ev.is_set()
