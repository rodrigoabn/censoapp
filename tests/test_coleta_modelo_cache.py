"""Modelo XLSX é carregado uma única vez por processo (`functools.cache`).

O arquivo do modelo é estático durante a execução; os call sites tratam o
retorno como somente leitura. O cache evita reabrir/reparsar o XLSX a cada
escola coletada.
"""

from __future__ import annotations

from apps.coleta_gestor.src import modelo as gestor_modelo
from src import modelo as cad_modelo


def test_modelo_de_cadastros_e_cacheado():
    cad_modelo.load_model.cache_clear()

    a = cad_modelo.load_model()
    b = cad_modelo.load_model()

    assert a is b
    assert cad_modelo.load_model.cache_info().hits >= 1


def test_modelo_do_gestor_e_cacheado():
    gestor_modelo.load_model.cache_clear()

    a = gestor_modelo.load_model()
    b = gestor_modelo.load_model()

    assert a is b
    assert gestor_modelo.load_model.cache_info().hits >= 1
