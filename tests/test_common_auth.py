"""Testes do módulo comum de autenticação (`apps/common/auth.py`) — Fase 4.1."""

from __future__ import annotations

import importlib

import pytest

from apps.common import auth as common_auth

MODULOS_AUTH_DOS_APPS = [
    "apps.coleta_cadastros_escolas.src.auth",
    "apps.coleta_gestor.src.auth",
    "apps.coleta_relatorios.src.auth",
    "apps.coleta_recibos_fechamento.src.auth",
]


def test_modulo_comum_tem_valores_esperados() -> None:
    assert common_auth.BASE_URL == "https://educacenso.inep.gov.br"
    assert common_auth.READ_ONLY is True


def test_assert_read_only_nao_levanta_quando_ligado() -> None:
    common_auth._assert_read_only()


def test_assert_read_only_levanta_com_mensagem_exata_quando_desligado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(common_auth, "READ_ONLY", False)
    with pytest.raises(RuntimeError) as excinfo:
        common_auth._assert_read_only()
    mensagem = "MODO LEITURA violado: operações de escrita no site estão proibidas."
    assert str(excinfo.value) == mensagem


@pytest.mark.parametrize("nome_modulo", MODULOS_AUTH_DOS_APPS)
def test_auth_dos_apps_reexporta_o_mesmo_objeto(nome_modulo: str) -> None:
    modulo = importlib.import_module(nome_modulo)
    assert modulo.BASE_URL == common_auth.BASE_URL
    assert modulo.READ_ONLY is True
    assert modulo._assert_read_only is common_auth._assert_read_only
