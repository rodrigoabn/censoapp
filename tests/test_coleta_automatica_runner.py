"""A rodada da Coleta Automática: sequência, tempos, falhas e interrupção."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from apps.coleta_automatica.src.etapas import Etapa
from apps.coleta_automatica.src.runner import executar_rodada


class _ZipperFalso:
    """Monta um 'artefato' de mentira e sabe os nomes dos arquivos."""

    def output_filename(self, prefix):
        return f"{prefix}_fake.bin"

    def pending_filename(self, prefix):
        return f"{prefix}_nao_coletadas_fake.xlsx"

    def build_xlsx(self, tmp_dir, model=None):
        return b"artefato-falso"

    def build_zip(self, tmp_dir):
        return b"artefato-falso"


def _etapa(chave, *, erro=None, coletadas=2, arquivos=("dados.csv",)):
    """Etapa falsa: o worker grava arquivos e preenche o shared como o real."""

    def worker(config, login, senha, escolas, stop_event, lock, shared, tmp_dir):
        shared["total"] = len(escolas)
        for nome in arquivos:
            (Path(tmp_dir) / nome).write_text("x", encoding="utf-8")
        if erro:
            shared["error"] = erro
        shared["count"] = coletadas
        shared["failures"] = (
            []
            if coletadas
            else [
                {
                    "codigo_inep": "33000001",
                    "nome_unidade": "Escola Um",
                    "motivo": "Falha no login",
                }
            ]
        )

    return Etapa(
        chave=chave,
        titulo=chave,
        pasta=chave,
        config={"zip_prefix": chave},
        zipper=_ZipperFalso(),
        worker=worker,
    )


def _rodar(etapas, *, escolas=None, stop_event=None, continuar_event=None, tmp_path=None):
    escolas = escolas or [{"codigo_inep": "33000001", "nome_unidade": "Escola Um"}]
    estado = {
        "resultados": [],
        "etapa_atual": None,
        "shared_etapa": None,
        "aguardando": None,
        "interrompida": False,
        "pacote": None,
    }
    executar_rodada(
        etapas,
        "cpf",
        "senha",
        escolas,
        stop_event=stop_event or threading.Event(),
        lock=threading.Lock(),
        estado=estado,
        pasta_base=tmp_path,
        continuar_event=continuar_event,
    )
    return estado


def test_rodada_roda_as_etapas_em_sequencia_e_mede_os_tempos(tmp_path):
    estado = _rodar([_etapa("a"), _etapa("b")], tmp_path=tmp_path)
    assert [r.chave for r in estado["resultados"]] == ["a", "b"]
    assert all(r.situacao == "concluida" for r in estado["resultados"])
    assert all(r.segundos >= 0 for r in estado["resultados"])
    assert all(r.caminho_artefato for r in estado["resultados"])


def test_artefato_de_cada_etapa_vai_para_o_disco(tmp_path):
    estado = _rodar([_etapa("a")], tmp_path=tmp_path)
    caminho = Path(estado["resultados"][0].caminho_artefato)
    assert caminho.exists()


def test_etapa_com_erro_do_worker_derruba_a_rodada(tmp_path):
    estado = _rodar(
        [_etapa("a", erro="browser morreu"), _etapa("b")], tmp_path=tmp_path
    )
    assert estado["resultados"][0].situacao == "falhou"
    assert estado["resultados"][0].motivo == "browser morreu"
    assert estado["resultados"][1].situacao == "nao_executada"
    assert estado["interrompida"] is True


def test_etapa_sem_coleta_pausa_a_rodada_e_espera_confirmacao(tmp_path):
    continuar = threading.Event()
    estado = {}

    def rodar():
        executar_rodada(
            [_etapa("a", coletadas=0), _etapa("b")],
            "cpf",
            "senha",
            [{"codigo_inep": "33000001", "nome_unidade": "Escola Um"}],
            stop_event=threading.Event(),
            lock=threading.Lock(),
            estado=estado,
            pasta_base=tmp_path,
            continuar_event=continuar,
        )

    t = threading.Thread(target=rodar, daemon=True)
    t.start()
    for _ in range(100):
        if estado.get("aguardando"):
            break
        time.sleep(0.05)
    assert estado["aguardando"] == "a"
    assert [r.situacao for r in estado["resultados"]] == ["concluida_sem_dados"]
    assert t.is_alive()  # a rodada está esperando o usuário

    continuar.set()
    t.join(timeout=10)
    assert [r.situacao for r in estado["resultados"]] == [
        "concluida_sem_dados",
        "concluida",
    ]


def test_interrupcao_entre_etapas_marca_nao_executada(tmp_path):
    stop = threading.Event()
    stop.set()
    estado = _rodar([_etapa("a"), _etapa("b")], stop_event=stop, tmp_path=tmp_path)
    assert [r.situacao for r in estado["resultados"]] == [
        "nao_executada",
        "nao_executada",
    ]
    assert estado["interrompida"] is True


def test_pacote_completo_reune_os_artefatos_em_pastas(tmp_path):
    from apps.coleta_automatica.src.runner import montar_pacote

    estado = _rodar([_etapa("a"), _etapa("b")], tmp_path=tmp_path)
    zip_path = montar_pacote(estado["resultados"], tmp_path)
    assert zip_path is not None and zip_path.exists()

    import zipfile

    with zipfile.ZipFile(zip_path) as z:
        nomes = z.namelist()
    assert any(n.startswith("a/") for n in nomes)
    assert any(n.startswith("b/") for n in nomes)


def test_rodada_sem_coleta_nao_gera_pacote(tmp_path):
    estado = _rodar([_etapa("a", coletadas=0)], tmp_path=tmp_path)
    assert estado["resultados"][0].caminho_artefato is None
    assert estado["pacote"] is None


def test_rodada_publica_que_terminou(tmp_path):
    estado = _rodar([_etapa("a")], tmp_path=tmp_path)
    assert estado["terminada"] is True
    assert estado["etapa_atual"] is None


def test_etapa_interrompida_no_meio_e_marcada_interrompida(tmp_path):
    """Interromper durante a etapa: a etapa não é "concluída" e a rodada para."""
    stop = threading.Event()

    def worker(config, login, senha, escolas, stop_event, lock, shared, tmp_dir):
        shared["total"] = len(escolas)
        shared["count"] = 1
        stop_event.set()  # o operador interrompe no meio da etapa

    etapa = Etapa(
        chave="a",
        titulo="a",
        pasta="a",
        config={"zip_prefix": "a"},
        zipper=_ZipperFalso(),
        worker=worker,
    )
    estado = _rodar([etapa, _etapa("b")], stop_event=stop, tmp_path=tmp_path)

    assert estado["resultados"][0].situacao == "interrompida"
    assert estado["interrompida"] is True
    assert estado["resultados"][1].situacao == "nao_executada"
    assert estado["pacote"] is None


def test_ultima_etapa_interrompida_nao_gera_pacote(tmp_path):
    """Interromper na ÚLTIMA etapa também impede o pacote completo."""
    stop = threading.Event()

    def worker(config, login, senha, escolas, stop_event, lock, shared, tmp_dir):
        shared["total"] = len(escolas)
        shared["count"] = 1
        stop_event.set()

    etapa = Etapa(
        chave="a",
        titulo="a",
        pasta="a",
        config={"zip_prefix": "a"},
        zipper=_ZipperFalso(),
        worker=worker,
    )
    estado = _rodar([etapa], stop_event=stop, tmp_path=tmp_path)

    assert estado["resultados"][0].situacao == "interrompida"
    assert estado["interrompida"] is True
    assert estado["pacote"] is None


def test_erro_ao_montar_o_artefato_encerra_a_rodada_com_erro(tmp_path):
    """Exceção na construção do artefato não pode travar a tela em "rodando"."""

    class _ZipperQuebrado:
        def output_filename(self, prefix):
            return "x.bin"

        def pending_filename(self, prefix):
            return "x.xlsx"

        def build_xlsx(self, tmp_dir, model=None):
            raise RuntimeError("disco cheio")

        def build_zip(self, tmp_dir):
            raise RuntimeError("disco cheio")

    etapa = Etapa(
        chave="a",
        titulo="a",
        pasta="a",
        config={"zip_prefix": "a"},
        zipper=_ZipperQuebrado(),
        worker=_etapa("a").worker,
    )
    estado = _rodar([etapa], tmp_path=tmp_path)

    assert estado["terminada"] is True
    assert estado["erro_rodada"] == "disco cheio"
    assert estado["resultados"][0].situacao == "falhou"


def test_limpar_temporarios_antigos_remove_a_pasta_orfa(tmp_path, monkeypatch):
    """Pastas de rodadas abandonadas não podem ficar para sempre no /tmp."""
    import os
    import time

    from apps.coleta_automatica.src import runner

    pasta = tmp_path / "coleta_automatica_tmp_orfã"
    pasta.mkdir()
    (pasta / "relatorio_alunos.zip").write_bytes(b"pII")
    antigo = time.time() - 48 * 3600
    os.utime(pasta, (antigo, antigo))

    monkeypatch.setattr(runner.tempfile, "gettempdir", lambda: str(tmp_path))
    removidas = runner.limpar_temporarios_antigos(horas=24)

    assert removidas == 1
    assert not pasta.exists()


def test_limpar_temporarios_antigos_preserva_a_pasta_recente(tmp_path, monkeypatch):
    """A pasta de uma rodada em uso (recente) não pode ser apagada."""
    import os
    import time

    from apps.coleta_automatica.src import runner

    pasta = tmp_path / "coleta_automatica_tmp_ativa"
    pasta.mkdir()
    agora = time.time()
    os.utime(pasta, (agora, agora))

    monkeypatch.setattr(runner.tempfile, "gettempdir", lambda: str(tmp_path))
    removidas = runner.limpar_temporarios_antigos(horas=24)

    assert removidas == 0
    assert pasta.exists()


# ── nova tentativa por escola (contextos da rodada) ────────────────────────


def test_rodada_liga_o_retry_por_escola_e_restaura_os_defaults(tmp_path):
    """Na rodada: 5 tentativas por escola (5 s) e 1 tentativa de navegação."""
    from apps.common import coleta, session

    vistos = []

    def worker(config, login, senha, escolas, stop_event, lock, shared, tmp_dir):
        vistos.append(
            (
                coleta.TENTATIVAS_TIMEOUT.get(),
                coleta.ESPERA_TENTATIVAS.get(),
                session.TENTATIVAS_NAVEGACAO.get(),
            )
        )
        shared["count"] = len(escolas)
        shared["failures"] = []

    etapa = Etapa(
        chave="b",
        titulo="b",
        pasta="b",
        config={"zip_prefix": "b"},
        zipper=_ZipperFalso(),
        worker=worker,
    )
    _rodar([etapa], tmp_path=tmp_path)

    assert vistos == [(5, 5.0, 1)]
    assert coleta.TENTATIVAS_TIMEOUT.get() == 1
    assert coleta.ESPERA_TENTATIVAS.get() == 5.0
    assert session.TENTATIVAS_NAVEGACAO.get() == 3


def test_contextos_da_rodada_voltam_ao_default_mesmo_com_erro_do_worker(tmp_path):
    from apps.common import coleta, session

    def worker(config, login, senha, escolas, stop_event, lock, shared, tmp_dir):
        raise RuntimeError("browser morreu")

    etapa = Etapa(
        chave="b",
        titulo="b",
        pasta="b",
        config={"zip_prefix": "b"},
        zipper=_ZipperFalso(),
        worker=worker,
    )
    estado = _rodar([etapa], tmp_path=tmp_path)

    assert estado["resultados"][0].situacao == "falhou"
    assert coleta.TENTATIVAS_TIMEOUT.get() == 1
    assert coleta.ESPERA_TENTATIVAS.get() == 5.0
    assert session.TENTATIVAS_NAVEGACAO.get() == 3
