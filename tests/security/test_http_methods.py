"""Testes de métodos HTTP inseguros/inesperados.

Não intrusivo: um pedido por método, sem corpo.
"""

from __future__ import annotations

import pytest

from conftest import TIMEOUT

pytestmark = pytest.mark.live


def test_trace_method_disabled(session, base_url):
    """TRACE/TRACK habilitado pode permitir Cross-Site Tracing."""
    resp = session.request("TRACE", base_url, timeout=TIMEOUT)
    assert resp.status_code in (403, 405, 501, 400), (
        f"Método TRACE não recusado (status {resp.status_code})."
    )


def test_track_method_disabled(session, base_url):
    resp = session.request("TRACK", base_url, timeout=TIMEOUT)
    assert resp.status_code in (403, 405, 501, 400), (
        f"Método TRACK não recusado (status {resp.status_code})."
    )


@pytest.mark.parametrize("method", ["PUT", "DELETE", "PATCH"])
def test_write_methods_have_no_effect(session, base_url, root_response, method):
    """A aplicação é leitura; métodos de escrita não devem MUTAR estado.

    Em *.streamlit.app o servidor estático (nginx) pode responder 200 com o
    mesmo index da SPA. Isso não é uma escrita — o crítico é que a resposta
    não indique processamento/mutação distinto do GET da raiz.
    """
    resp = session.request(method, base_url, timeout=TIMEOUT)

    # Recusa explícita: comportamento ideal.
    if resp.status_code in (403, 405, 501, 400, 404):
        return

    # 2xx só é aceitável se for exatamente o index estático do GET (sem efeito).
    assert resp.status_code < 300, (
        f"Método {method} retornou status inesperado {resp.status_code}."
    )
    assert resp.content == root_response.content, (
        f"[atenção] {method} retornou corpo diferente do GET — possível "
        f"processamento de escrita (status {resp.status_code})."
    )
