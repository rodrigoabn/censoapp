"""Portão de autenticação do HUB (`auth_gate`).

Cobre os três modos com um `st` falso, no estilo dos demais testes de frontend:
a lógica mora em `auth_gate.exigir_autenticacao`, que recebe o módulo `st` como
parâmetro e chama `st.stop()` quando o acesso não está liberado. Cada modo é
testado no limite: quem não entrou é barrado, quem entrou prossegue e "Sair"
revoga a sessão.
"""

from __future__ import annotations

import pytest

from auth_gate import exigir_autenticacao, modo_autenticacao


class _ParouExecucao(Exception):
    """Equivale ao `st.stop()`: interrompe a execução do script."""


class _EstadoFalso(dict):
    """session_state mínimo (acesso por chave)."""


class _UsuarioFalso:
    def __init__(self, logado=False, nome="", email=""):
        self.is_logged_in = logado
        self.name = nome
        self.email = email


class _SidebarFalso:
    def __init__(self, st):
        self._st = st

    def caption(self, texto):
        self._st.captions.append(texto)

    def markdown(self, texto, **kwargs):
        self._st.sidebar_markdowns.append(texto)

    def button(self, label, **kwargs):
        self._st.botoes_sidebar.append(label)
        return self._st.respostas_botoes.get(label, False)


class _StFalso:
    def __init__(
        self,
        secrets=None,
        logado=False,
        nome="",
        email="",
        respostas=None,
        respostas_input=None,
        estado=None,
        secrets_ruim=False,
    ):
        self._secrets = None
        if not secrets_ruim:
            self.secrets = secrets if secrets is not None else {}
        self.user = _UsuarioFalso(logado, nome, email)
        self.session_state = estado if estado is not None else _EstadoFalso()
        self.sidebar = _SidebarFalso(self)
        self.respostas_botoes = respostas or {}
        self.respostas_input = respostas_input or {}
        self.erros, self.captions, self.sidebar_markdowns = [], [], []
        self.markdowns = []
        self.botoes, self.botoes_sidebar, self.inputs = [], [], []
        self.login_chamadas, self.logout_chamadas = 0, 0

    @property
    def secrets(self):
        """`secrets_ruim=True` simula ambiente sem secrets (st.secrets levanta)."""
        if self._secrets is None:
            raise RuntimeError("secrets indisponível")
        return self._secrets

    @secrets.setter
    def secrets(self, valor):
        self._secrets = valor

    def error(self, msg):
        self.erros.append(msg)

    def markdown(self, body, **kwargs):
        self.markdowns.append(body)

    def caption(self, texto, **kwargs):
        self.captions.append(texto)

    def button(self, label, **kwargs):
        self.botoes.append(label)
        return self.respostas_botoes.get(label, False)

    def text_input(self, label, **kwargs):
        self.inputs.append((label, kwargs))
        return self.respostas_input.get(label, "")

    def stop(self):
        raise _ParouExecucao()

    def login(self):
        self.login_chamadas += 1

    def logout(self):
        self.logout_chamadas += 1

    def rerun(self):
        raise _ParouExecucao()


def test_modo_detectado_pela_configuracao():
    assert modo_autenticacao({}, {}) == "aberto"
    assert modo_autenticacao({"auth": {}}, {}) == "oidc"
    assert modo_autenticacao({"auth_simples": {"senha": "x"}}, {}) == "senha"


def test_modo_forcado_por_env_e_valor_invalido():
    assert modo_autenticacao({"auth": {}}, {"CENSO_AUTH_MODE": "aberto"}) == "aberto"
    with pytest.raises(ValueError):
        modo_autenticacao({}, {"CENSO_AUTH_MODE": "banana"})


def test_aberto_prossegue_e_avisa_na_sidebar():
    st = _StFalso()
    exigir_autenticacao(st, env={})
    assert st.erros == []
    assert st.login_chamadas == 0
    assert any("autenticação" in c.lower() and "não" in c.lower() for c in st.captions)


def test_oidc_nao_logado_bloqueia_e_oferece_entrar():
    st = _StFalso(secrets={"auth": {"client_id": "x"}})
    with pytest.raises(_ParouExecucao):
        exigir_autenticacao(st, env={})
    assert "Entrar" in st.botoes
    assert st.login_chamadas == 0  # só redireciona depois do clique


def test_oidc_clique_em_entrar_chama_login():
    st = _StFalso(secrets={"auth": {}}, respostas={"Entrar": True})
    with pytest.raises(_ParouExecucao):
        exigir_autenticacao(st, env={})
    assert st.login_chamadas == 1


def test_oidc_logado_mostra_usuario_e_sair_desloga():
    st = _StFalso(
        secrets={"auth": {}},
        logado=True,
        nome="Fulana de Tal",
        email="fulana@seduct.gov.br",
        respostas={"Sair": True},
    )
    with pytest.raises(_ParouExecucao):  # st.rerun() depois de deslogar
        exigir_autenticacao(st, env={})
    assert any("fulana@seduct.gov.br" in m for m in st.sidebar_markdowns)
    assert st.logout_chamadas == 1


def test_oidc_forcado_por_env_sem_auth_fecha_por_padrao():
    st = _StFalso()
    with pytest.raises(_ParouExecucao):
        exigir_autenticacao(st, env={"CENSO_AUTH_MODE": "oidc"})
    assert st.erros


def test_senha_errada_bloqueia_e_nao_libera():
    st = _StFalso(
        secrets={"auth_simples": {"senha": "correta"}},
        respostas={"Entrar": True},
        respostas_input={"Senha de acesso": "errada"},
    )
    with pytest.raises(_ParouExecucao):
        exigir_autenticacao(st, env={})
    assert st.erros
    assert not st.session_state.get("auth_ok")


def test_senha_correta_libera_a_sessao():
    st = _StFalso(
        secrets={"auth_simples": {"senha": "correta"}},
        respostas={"Entrar": True},
        respostas_input={"Senha de acesso": "correta"},
    )
    with pytest.raises(_ParouExecucao):  # st.rerun() logo após liberar
        exigir_autenticacao(st, env={})
    assert st.session_state.get("auth_ok") is True


def test_senha_logado_sair_revoga():
    estado = _EstadoFalso(auth_ok=True)
    st = _StFalso(
        secrets={"auth_simples": {"senha": "correta"}},
        estado=estado,
        respostas={"Sair": True},
    )
    with pytest.raises(_ParouExecucao):  # st.rerun() depois de revogar
        exigir_autenticacao(st, env={})
    assert estado.get("auth_ok") is False


def test_senha_com_acentos_funciona():
    st = _StFalso(
        secrets={"auth_simples": {"senha": "Censo@2026ç"}},
        respostas={"Entrar": True},
        respostas_input={"Senha de acesso": "Censo@2026ç"},
    )
    with pytest.raises(_ParouExecucao):  # st.rerun() logo após liberar
        exigir_autenticacao(st, env={})
    assert st.session_state.get("auth_ok") is True


def test_senha_forcada_sem_config_mostra_erro_claro():
    st = _StFalso()
    with pytest.raises(_ParouExecucao):
        exigir_autenticacao(st, env={"CENSO_AUTH_MODE": "senha"})
    assert st.erros and "auth_simples" in st.erros[0]


def test_senha_configurada_vazia_mostra_erro_claro():
    st = _StFalso(secrets={"auth_simples": {}})
    with pytest.raises(_ParouExecucao):
        exigir_autenticacao(st, env={})
    assert st.erros and "senha" in st.erros[0].lower()


def test_secrets_indisponivel_nao_derruba_o_hub():
    st = _StFalso(secrets_ruim=True)
    exigir_autenticacao(st, env={})  # cai no modo aberto, sem exceção
    assert st.erros == []
    assert any("não configurada" in c for c in st.captions)


def test_authlib_disponivel_para_o_modo_oidc():
    """st.login() (modo oidc) exige Authlib (extra "auth" do streamlit)."""
    from streamlit.auth_util import is_authlib_installed

    assert is_authlib_installed()
