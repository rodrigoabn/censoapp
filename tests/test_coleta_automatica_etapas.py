"""Registro das 6 etapas da Coleta Automática."""

from __future__ import annotations

import pytest

from apps.coleta_automatica.src.etapas import ETAPAS, etapa_por_chave


def test_registro_tem_as_seis_etapas_na_ordem_da_rodada():
    assert [e.chave for e in ETAPAS] == [
        "cadastros_escolas",
        "gestor",
        "relatorios_turmas",
        "relatorios_alunos",
        "relatorios_profissionais",
        "recibos",
    ]
    assert [e.titulo for e in ETAPAS] == [
        "Cadastros das escolas",
        "Cadastro do gestor",
        "Relatórios de Turmas",
        "Relatórios de Alunos",
        "Relatórios de Profissionais Escolares",
        "Recibos de Fechamento",
    ]


def test_cada_etapa_aponta_para_o_app_de_origem():
    by_chave = {e.chave: e for e in ETAPAS}
    assert by_chave["cadastros_escolas"].config["state_prefix"] == "ws_"
    assert by_chave["cadastros_escolas"].config["zip_prefix"] == "cadastro_escola"
    assert by_chave["gestor"].config["state_prefix"] == "cg_"
    assert by_chave["gestor"].config["zip_prefix"] == "vinculo_gestor"
    assert by_chave["relatorios_turmas"].config["state_prefix"] == "rt_"
    assert by_chave["relatorios_alunos"].config["state_prefix"] == "ra_"
    assert by_chave["relatorios_profissionais"].config["state_prefix"] == "rp_"
    assert by_chave["recibos"].config["state_prefix"] == "rf_"


def test_worker_de_cada_etapa_aceita_o_config_primeiro():
    import inspect

    for etapa in ETAPAS:
        params = list(inspect.signature(etapa.worker).parameters)
        assert params[0] == "config", (etapa.chave, params)
        assert params[1:4] == ["login", "senha", "escolas"], (etapa.chave, params)


def test_zipper_de_cada_etapa_monta_o_artefato():
    for etapa in ETAPAS:
        construtor = etapa.config.get("construtor_arquivo", "build_zip")
        assert hasattr(etapa.zipper, construtor), (etapa.chave, construtor)
        assert hasattr(etapa.zipper, "output_filename")


def test_etapa_por_chave():
    assert etapa_por_chave("gestor").titulo == "Cadastro do gestor"
    with pytest.raises(KeyError):
        etapa_por_chave("inexistente")
