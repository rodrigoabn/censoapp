"""Pina o feedback final da verificação conforme o conteúdo dos resultados.

Caso relatado (2026-10-20): com zero inconsistências, o clique em
"Iniciar Verificação de Inconsistências" não mostrava nada na tela — a lista
vazia não caía em nenhum ramo da Etapa 3. Resultados com status ``"erro"``
(ex.: falha ao ler o arquivo do gestor) também eram descartados em silêncio.

Os testes exercitam o frontend real via ``AppTest``, com o estado da sessão
semeado como ficaria logo após a validação (``finalizado=True`` e
``resultados`` preenchido).
"""

from __future__ import annotations

from streamlit.testing.v1 import AppTest


def _rodar(config_key: str, resultados: list[dict]) -> AppTest:
    def _script(config_key, resultados):
        import pandas as pd
        import streamlit as st

        from apps.verificacao_inconsistencias.src.frontend import render_validation_frontend
        from apps.verificacao_inconsistencias.src.validations import VALIDATIONS

        config = VALIDATIONS[config_key]
        prefix = config["state_prefix"]
        ss = st.session_state
        ss[f"{prefix}estrutura_ok"] = True
        ss[f"{prefix}escolas"] = [{"codigo_inep": "1", "nome_unidade": "Escola Um"}]
        ss[f"{prefix}colunas_validadas"] = True
        vazio = pd.DataFrame({"x": []})
        for sufixo in ("df_unificado", "df_aee", "df_atv", "df_curricular", "df_escolarizacao"):
            ss[f"{prefix}{sufixo}"] = vazio
        ss[f"{prefix}arquivo_bytes"] = b"conteudo"
        ss[f"{prefix}resultados"] = resultados
        ss[f"{prefix}finalizado"] = True
        render_validation_frontend(config)

    at = AppTest.from_function(
        _script, args=(config_key, resultados), default_timeout=60
    )
    return at.run()


def test_sem_inconsistencias_mostra_mensagem():
    at = _rodar("turmas", [])
    assert not at.exception
    mensagens = [s.value for s in at.success]
    assert any("Nenhuma inconsistência encontrada" in m for m in mensagens), mensagens


def test_com_inconsistencia_mostra_total_e_download():
    resultados = [{
        "codigo_inep": "1",
        "nome_unidade": "Escola Um",
        "nome_turma": "2BM02",
        "status": "inconsistente",
        "erros": ["Divergência entre Sigla e Etapa"],
        "detalhes": "Divergência entre Sigla e Etapa",
    }]
    at = _rodar("turmas", resultados)
    assert not at.exception
    markdowns = [m.value for m in at.markdown]
    assert any("Total de Inconsistencias:** 1" in m for m in markdowns), markdowns
    labels = [d.label for d in at.get("download_button")]
    assert "Relatório de Inconsistências (XLSX)" in labels, labels


def test_resultado_com_erro_mostra_erro():
    resultados = [{
        "codigo_inep": "",
        "nome_unidade": "",
        "tipo_validacao": "gestor",
        "status": "erro",
        "detalhes": "Aba 'Vínculo do gestor' não encontrada no arquivo.",
    }]
    at = _rodar("turmas", resultados)
    assert not at.exception
    erros = [e.value for e in at.error]
    assert any("não encontrada no arquivo" in e for e in erros), erros
