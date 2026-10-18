"""Logging rotativo do HUB (`logging_setup`).

Cobre o contrato visível: arquivo criado no diretório resolvido (param ou
`CENSO_LOG_DIR`), linha formatada, nível resolvido por `CENSO_LOG_LEVEL`,
rotação por tamanho e idempotência (cada rerun do Streamlit chama a função de
novo e não pode duplicar handlers).

O handler é único por processo (semântica de produção); por isso a fixture
autouse remove o handler marcado ao fim de cada teste, isolando os diretórios.
"""

from __future__ import annotations

import logging

import pytest

from logging_setup import configurar_logging


def _remover_handlers_do_hub() -> None:
    raiz = logging.getLogger()
    for handler in list(raiz.handlers):
        if getattr(handler, "_censoapp_handler", False):
            handler.close()
            raiz.removeHandler(handler)


@pytest.fixture(autouse=True)
def _limpa_handler_do_hub():
    """Isola os diretórios: o handler é único por processo (inclusive o que o
    boot do HUB pode ter criado antes, no diretório do repo)."""
    _remover_handlers_do_hub()
    yield
    _remover_handlers_do_hub()


def _hub_handlers() -> list:
    return [h for h in logging.getLogger().handlers if getattr(h, "_censoapp_handler", False)]


def _flush() -> None:
    for handler in logging.getLogger().handlers:
        handler.flush()


def test_cria_arquivo_e_formata_linha(tmp_path):
    caminho = configurar_logging(log_dir=tmp_path, env={})

    assert caminho == tmp_path / "censoapp.log"
    logging.getLogger("coleta_teste").info("escola 123 coletada")
    _flush()

    conteudo = caminho.read_text(encoding="utf-8")
    assert "INFO coleta_teste escola 123 coletada" in conteudo


def test_idempotente_entre_chamadas(tmp_path):
    configurar_logging(log_dir=tmp_path, env={})
    configurar_logging(log_dir=tmp_path, env={})

    assert len(_hub_handlers()) == 1


def test_rotaciona_ao_exceder_max_bytes(tmp_path):
    caminho = configurar_logging(log_dir=tmp_path, env={})
    handler = _hub_handlers()[0]
    handler.maxBytes = 300  # exercita a rotação com um volume pequeno

    log = logging.getLogger("coleta_teste")
    for i in range(50):
        log.info("linha de log número %02d com tamanho suficiente", i)
    _flush()

    assert caminho.exists()
    assert (tmp_path / "censoapp.log.1").exists()


def test_env_resolve_diretorio_e_nivel(tmp_path):
    caminho = configurar_logging(env={"CENSO_LOG_DIR": str(tmp_path), "CENSO_LOG_LEVEL": "WARNING"})

    assert caminho == tmp_path / "censoapp.log"
    assert logging.getLogger().level == logging.WARNING

    log = logging.getLogger("coleta_teste")
    log.debug("não deve aparecer")
    _flush()
    assert "não deve aparecer" not in caminho.read_text(encoding="utf-8")
