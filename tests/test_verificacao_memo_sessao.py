"""Pina o memo por sessão dos relatórios com PII (`_memo_sessao`).

Fase 6.7: as quatro conversões com PII deixaram de usar `@st.cache_data`
(cache global, retenção indevida) e passaram a memoizar em
`st.session_state` por identidade do insumo; só o agregado de cor/raça
(não individualiza) mantém cache global, com TTL curto.
"""

from __future__ import annotations

from apps.verificacao_inconsistencias.src import frontend


def test_reusa_enquanto_o_insumo_nao_muda():
    ss = {}
    insumo = object()
    chamadas = []

    def construtor():
        chamadas.append(1)
        return b"bytes"

    assert frontend._memo_sessao(ss, "k", insumo, construtor) == b"bytes"
    assert frontend._memo_sessao(ss, "k", insumo, construtor) == b"bytes"
    assert len(chamadas) == 1


def test_reconstroi_quando_o_insumo_muda():
    ss = {}
    chamadas = []

    def construtor():
        chamadas.append(1)
        return b"bytes"

    frontend._memo_sessao(ss, "k", object(), construtor)
    frontend._memo_sessao(ss, "k", object(), construtor)
    assert len(chamadas) == 2


def test_insumo_none_e_memoizado():
    ss = {}
    chamadas = []

    def construtor():
        chamadas.append(1)
        return b"bytes"

    frontend._memo_sessao(ss, "k", None, construtor)
    frontend._memo_sessao(ss, "k", None, construtor)
    assert len(chamadas) == 1


def test_somente_o_agregado_continua_com_cache_global():
    assert not hasattr(frontend._unificado_xlsx, "clear")
    assert not hasattr(frontend._build_xlsx, "clear")
    assert not hasattr(frontend._duplicadas_xlsx, "clear")
    assert not hasattr(frontend._sem_cpf_xlsx, "clear")
    assert hasattr(frontend._levantamento_cor_raca_xlsx, "clear")
