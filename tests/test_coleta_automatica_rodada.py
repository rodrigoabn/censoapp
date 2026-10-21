"""A tela da rodada (em andamento e pausada), testada com um `st` falso.

O `AppTest` não serve aqui: a tela da rodada usa `st.fragment(run_every=0.5)`
para redesenhar o relógio, e o fragmento não é executado pelo AppTest. O teste
usa um `st` falso, como `tests/test_common_ui.py` faz com os helpers comuns.
"""

from __future__ import annotations

import copy
import threading
from datetime import datetime

import pytest

from apps.coleta_automatica.src import frontend
from apps.coleta_automatica.src.runner import ResultadoEtapa


class _Rerun(Exception):
    """Interrompe o script como o `st.rerun()` real."""


class _ColunaFalsa:
    """Encaminha tudo para o `st` falso e funciona como gerenciador de contexto."""

    def __init__(self, st, ao_entrar=None, ao_sair=None):
        self._st = st
        self._ao_entrar = ao_entrar
        self._ao_sair = ao_sair

    def __enter__(self):
        if self._ao_entrar is not None:
            self._ao_entrar(self._st)
        return self

    def __exit__(self, *exc):
        if self._ao_sair is not None:
            self._ao_sair(self._st)
        return False

    def __getattr__(self, nome):
        return getattr(self._st, nome)


class _StFalso:
    def __init__(self, estado):
        self.session_state = estado
        self.markdowns = []
        self.writes = []
        self.subheaders = []
        self.captions = []
        self.dividers = 0
        self.containers = []
        self._pilha = []
        self.botoes = []
        self.avisos = []
        self.downloads = []
        self.clicar_em = None
        self.rerun_chamado = False
        self.profundidade_no_rerun = None

    @property
    def texto(self) -> str:
        """Todo o texto escrito na tela (markdown, write, subheader, caption)."""
        partes = self.markdowns + self.writes + self.subheaders + self.captions
        return " ".join(str(p) for p in partes)

    def markdown(self, body, **kwargs):
        self.markdowns.append(body)

    def write(self, body, **kwargs):
        self.writes.append(body)

    def subheader(self, body, **kwargs):
        self.subheaders.append(body)

    def caption(self, body, **kwargs):
        self.captions.append(body)

    def divider(self, **kwargs):
        self.dividers += 1

    def warning(self, msg, **kwargs):
        self.avisos.append(msg)

    def error(self, msg, **kwargs):
        self.avisos.append(msg)

    def text_input(self, label, **kwargs):
        return "12345678900"

    def file_uploader(self, label, **kwargs):
        return "lista.xlsx"

    def checkbox(self, label, **kwargs):
        return True

    def button(self, label, **kwargs):
        # A profundidade diz em quantos containers o botão foi criado.
        self.botoes.append((label, kwargs, len(self._pilha)))
        key = kwargs.get("key")
        if key is not None and key in self.session_state:
            # O Streamlit copia o valor da sessão para o widget de mesma chave
            # (deepcopy) — um threading.Event não é copiável e a tela quebra.
            copy.deepcopy(self.session_state[key])
        return kwargs.get("key") == self.clicar_em

    def download_button(self, label, **kwargs):
        self.downloads.append((label, kwargs))
        return False

    def columns(self, n, **kwargs):
        if isinstance(n, int):
            n = [1] * n
        return [_ColunaFalsa(self) for _ in range(len(n))]

    def container(self, **kwargs):
        self.containers.append(kwargs)
        return _ColunaFalsa(
            self,
            ao_entrar=lambda st: st._pilha.append(kwargs),
            ao_sair=lambda st: st._pilha.pop(),
        )

    def rerun(self):
        # A profundidade no momento do rerun diz de onde ele saiu: um rerun
        # de dentro de um container deixa o card aberto e o frontend passa a
        # exibir restos da tela anterior junto com a nova.
        self.profundidade_no_rerun = len(self._pilha)
        self.rerun_chamado = True
        raise _Rerun()


def _rodada(estado_extra=None):
    """Estado de sessão de uma rodada em andamento."""
    estado = {
        "ca_running": True,
        "ca_finalized": False,
        "ca_inicio": datetime(2026, 10, 20, 21, 15, 3),
        "ca_lock": threading.Lock(),
        "ca_stop": threading.Event(),
        "ca_continuar_event": threading.Event(),
        "ca_estado": {
            "resultados": [],
            "etapa_atual": None,
            "shared_etapa": None,
            "aguardando": None,
            "interrompida": False,
            "pacote": None,
            "terminada": False,
            "etapas_selecionadas": ["cadastros_escolas", "gestor", "recibos"],
        },
    }
    if estado_extra:
        estado.update(estado_extra)
    return estado


@pytest.fixture(autouse=True)
def _sem_sleep(monkeypatch):
    """Nenhum `sleep` na tela da rodada (o redesenho é do fragmento)."""
    assert not hasattr(frontend, "time"), "a tela da rodada não deve dormir"


def test_tela_pausada_pergunta_ao_usuario_e_oferece_continuar(monkeypatch):
    """A pausa precisa mostrar a pergunta e o botão Continuar (sem quebrar a tela)."""
    estado = _rodada()
    estado["ca_estado"]["aguardando"] = "cadastros_escolas"
    st_falso = _StFalso(estado)
    monkeypatch.setattr(frontend, "st", st_falso)

    frontend._tela_rodada(estado["ca_estado"])

    rotulos = [b[0] for b in st_falso.botoes]
    assert "Continuar" in rotulos
    assert "Encerrar a rodada" in rotulos
    # a pergunta mostra o título da etapa, não a chave interna
    assert any("Cadastros das escolas" in a for a in st_falso.avisos)
    assert not any("cadastros_escolas" in a for a in st_falso.avisos)


def test_botao_continuar_dispara_o_evento_e_nao_colide_com_a_chave_do_widget(monkeypatch):
    """A chave do botão não pode ser a mesma que guarda o Event da rodada.

    Streamlit copia (deepcopy) o valor da sessão para o widget com a mesma
    chave — um `threading.Event` não é copiável e a tela quebraria.
    """
    estado = _rodada()
    estado["ca_estado"]["aguardando"] = "gestor"
    st_falso = _StFalso(estado)
    st_falso.clicar_em = "ca_continuar"
    monkeypatch.setattr(frontend, "st", st_falso)

    frontend._tela_rodada(estado["ca_estado"])

    evento = estado["ca_continuar_event"]
    assert evento.is_set(), "o botão Continuar não disparou o Event da rodada"
    # A chave do widget é diferente da chave que guarda o Event.
    assert "ca_continuar" not in estado


def test_botao_de_interromper_fica_dentro_do_cartao_do_relogio(monkeypatch):
    """O botão de interromper nasce dentro do cartão do relógio."""
    estado = _rodada()
    st_falso = _StFalso(estado)
    monkeypatch.setattr(frontend, "st", st_falso)

    frontend._tela_rodada(estado["ca_estado"])

    botoes = [b for b in st_falso.botoes if b[0] == "⛔ Interromper rodada"]
    assert botoes, "o botão de interromper não foi criado"
    assert botoes[0][2] > 0, "o botão ficou fora do cartão do relógio"


def test_botoes_de_pausa_ficam_dentro_do_cartao_do_relogio(monkeypatch):
    """Na pausa, Continuar e Encerrar também ficam dentro do cartão."""
    estado = _rodada()
    estado["ca_estado"]["aguardando"] = "cadastros_escolas"
    st_falso = _StFalso(estado)
    monkeypatch.setattr(frontend, "st", st_falso)

    frontend._tela_rodada(estado["ca_estado"])

    for rotulo in ("Continuar", "Encerrar a rodada"):
        botao = [b for b in st_falso.botoes if b[0] == rotulo]
        assert botao, f"o botão {rotulo} não foi criado"
        assert botao[0][2] > 0, f"o botão {rotulo} ficou fora do cartão"


def test_linha_da_escola_atual_entra_no_cartao_do_relogio(monkeypatch):
    """A linha da escola em coleta fica dentro do cartão do relógio."""
    estado = _rodada()
    estado["ca_estado"]["shared_etapa"] = {
        "current": (1, 2, "CEM ALDEIA", "33099510"),
        "count": 0,
    }
    st_falso = _StFalso(estado)
    monkeypatch.setattr(frontend, "st", st_falso)

    frontend._tela_rodada(estado["ca_estado"])

    assert any("Escola atual: CEM ALDEIA" in str(m) for m in st_falso.markdowns)


def test_cartao_avisa_a_nova_tentativa_da_escola(monkeypatch):
    """O usuário precisa ver que a MESMA escola está sendo repetida."""
    estado = _rodada()
    estado["ca_estado"]["shared_etapa"] = {
        "current": None,
        "aviso": ("33099510", "CEM ALDEIA", "nova tentativa 2 de 5 (timeout)"),
        "count": 0,
    }
    st_falso = _StFalso(estado)
    monkeypatch.setattr(frontend, "st", st_falso)

    frontend._tela_rodada(estado["ca_estado"])

    html = " ".join(str(m) for m in st_falso.markdowns)
    assert "CEM ALDEIA (33099510): nova tentativa 2 de 5 (timeout)" in html


def test_cartao_sem_aviso_nao_mostra_nova_tentativa(monkeypatch):
    estado = _rodada()
    estado["ca_estado"]["shared_etapa"] = {
        "current": None,
        "aviso": None,
        "count": 0,
    }
    st_falso = _StFalso(estado)
    monkeypatch.setattr(frontend, "st", st_falso)

    frontend._tela_rodada(estado["ca_estado"])

    html = " ".join(str(m) for m in st_falso.markdowns)
    assert "nova tentativa" not in html


def test_relogio_alinha_os_blocos_pela_base(monkeypatch):
    """O horário de início fica na linha do relógio (alinhamento pela base)."""
    estado = _rodada()
    st_falso = _StFalso(estado)
    monkeypatch.setattr(frontend, "st", st_falso)

    frontend._tela_rodada(estado["ca_estado"])

    html = " ".join(str(m) for m in st_falso.markdowns)
    assert "align-items:flex-end" in html


def test_tabela_mostra_a_etapa_em_andamento_e_as_pendentes(monkeypatch):
    """A tabela lista as etapas selecionadas, inclusive as que não rodaram."""
    estado = _rodada()
    estado["ca_estado"]["etapa_atual"] = "gestor"
    estado["ca_estado"]["shared_etapa"] = {
        "current": (1, 2, "Escola Alfa", "33000001"),
        "count": 0,
    }
    estado["ca_estado"]["resultados"] = [
        ResultadoEtapa(
            chave="cadastros_escolas",
            titulo="Cadastros das escolas",
            situacao="concluida",
            segundos=192.0,
        )
    ]
    st_falso = _StFalso(estado)
    monkeypatch.setattr(frontend, "st", st_falso)

    frontend._tela_rodada(estado["ca_estado"])

    texto = st_falso.texto
    assert "Cadastros das escolas" in texto
    assert "Concluída" in texto
    assert "Cadastro do gestor" in texto  # a etapa em andamento
    assert "Em andamento" in texto
    assert "Pendente" in texto  # a etapa que ainda vai rodar


def test_tabela_tem_os_cabecalhos_pedidos(monkeypatch):
    """A tabela tem as colunas: Tipo de dados | Status | Tempo | Arquivo |
    Dados | Pendências."""
    estado = _rodada()
    st_falso = _StFalso(estado)
    monkeypatch.setattr(frontend, "st", st_falso)

    frontend._tela_rodada(estado["ca_estado"])

    cabecalho = " ".join(st_falso.captions)
    for titulo in ("Tipo de dados", "Status", "Tempo", "Arquivo", "Dados", "Pendências"):
        assert titulo in cabecalho, titulo


def test_tabela_usa_a_estrutura_do_mockup(monkeypatch):
    """Título como subheader, uma linha divisória por etapa e status com bolinha."""
    estado = _rodada()
    st_falso = _StFalso(estado)
    monkeypatch.setattr(frontend, "st", st_falso)

    frontend._tela_rodada(estado["ca_estado"])

    assert "Tempo por aplicação" in st_falso.subheaders
    # 1 divisória do cabeçalho + 1 por etapa selecionada
    assert st_falso.dividers == 1 + len(estado["ca_estado"]["etapas_selecionadas"])
    # o status vem com a bolinha colorida
    assert "🟡" in st_falso.texto


def test_botoes_de_download_da_tabela_sao_cha_maos_baixar(monkeypatch, tmp_path):
    """Os downloads da tabela são rotulados "Baixar" (colunas Dados/Pendências)."""
    artefato = tmp_path / "cadastro_escola_educacenso_21-10-2026.xlsx"
    artefato.write_bytes(b"xlsx")
    estado = _rodada()
    estado["ca_estado"]["resultados"] = [
        ResultadoEtapa(
            chave="cadastros_escolas",
            titulo="Cadastros das escolas",
            situacao="concluida",
            segundos=1.0,
            caminho_artefato=str(artefato),
        )
    ]
    st_falso = _StFalso(estado)
    monkeypatch.setattr(frontend, "st", st_falso)

    frontend._tela_rodada(estado["ca_estado"])

    rotulos = [d[0] for d in st_falso.downloads]
    assert rotulos == ["Baixar"]
    # o nome do arquivo baixado é o do artefato
    assert st_falso.downloads[0][1]["file_name"] == artefato.name


def test_motivo_da_falha_e_escapado(monkeypatch):
    """O motivo da falha vem do site: precisa ser escapado antes do HTML."""
    estado = _rodada()
    estado["ca_estado"]["resultados"] = [
        ResultadoEtapa(
            chave="gestor",
            titulo="Cadastro do gestor",
            situacao="falhou",
            segundos=1.0,
            motivo="<b>Escola & Cia</b>",
        )
    ]
    st_falso = _StFalso(estado)
    monkeypatch.setattr(frontend, "st", st_falso)

    frontend._tela_rodada(estado["ca_estado"])

    texto = st_falso.texto
    assert "<b>Escola & Cia</b>" not in texto
    assert "&lt;b&gt;" in texto or "Escola &amp; Cia" in texto


def test_a_rodada_e_redesenhada_por_fragmento(monkeypatch):
    """A rodada NÃO pode abortar o script a cada ciclo.

    O padrão antigo (`sleep` + `st.rerun()` no meio da execução) deixava a
    árvore de elementos do frontend com restos da tela anterior: as
    "Orientações" e o card "Aplicações a coletar" reapareciam junto com a
    tela da rodada. O redesenho é feito por um fragmento, que limpa e
    redesenha só os elementos dele.
    """
    import inspect

    fonte = inspect.getsource(frontend._tela_rodada)
    assert "st.rerun" not in fonte, "a tela da rodada não pode abortar o script"
    assert "time.sleep" not in fonte, "a tela da rodada não pode dormir no script"
    assert hasattr(frontend, "_fragmento_rodada")


def test_render_chama_o_fragmento_durante_a_rodada(monkeypatch):
    """Com a rodada em andamento, a tela é desenhada pelo fragmento."""
    estado = _rodada()
    st_falso = _StFalso(estado)
    monkeypatch.setattr(frontend, "st", st_falso)

    chamado = []
    monkeypatch.setattr(frontend, "_fragmento_rodada", lambda: chamado.append(True))

    frontend.render_coleta_automatica_frontend()

    assert chamado, "a rodada em andamento não usou o fragmento"


def test_rerun_da_rodada_sai_fora_do_card(monkeypatch):
    """O rerun que inicia a rodada não pode sair de dentro de um card.

    Com o card aberto, o frontend passa a exibir o resto do formulário
    (Orientações e "Aplicações a coletar") junto com a tela da rodada.
    """
    estado = {"ca_running": False}
    st_falso = _StFalso(estado)
    st_falso.clicar_em = "ca_executar"
    monkeypatch.setattr(frontend, "st", st_falso)
    monkeypatch.setattr(
        frontend, "read_school_list", lambda _arquivo: [{"codigo": "1", "nome": "E"}]
    )
    monkeypatch.setattr(frontend, "executar_rodada", lambda *a, **k: None)

    with pytest.raises(_Rerun):
        frontend._tela_formulario()

    assert st_falso.profundidade_no_rerun == 0, (
        "o rerun da rodada saiu de dentro de um card"
    )
