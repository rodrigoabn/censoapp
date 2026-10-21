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
        textos=None,
    )


def _rodar(etapas, *, stop_event=None, continuar_event=None, tmp_path=None):
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
        [{"codigo_inep": "33000001", "nome_unidade": "Escola Um"}],
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
