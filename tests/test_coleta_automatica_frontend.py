"""A tela da Coleta Automática: formulário, seleção e estados da rodada."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

_RAIZ = Path(__file__).resolve().parents[1]


def _script():
    from apps.coleta_automatica.src.frontend import render_coleta_automatica_frontend

    render_coleta_automatica_frontend()


def _app():
    return AppTest.from_function(_script, default_timeout=60).run()


def test_formulario_tem_credenciais_lista_e_selecao():
    at = _app()
    assert not at.exception
    rotulos = [t.label for t in at.text_input]
    assert any("Login" in r for r in rotulos)
    assert any("Senha" in r for r in rotulos)
    assert len(at.file_uploader) == 1
    # 6 opções selecionáveis + 1 botão Executar
    assert len(at.checkbox) == 6
    assert any(b.label == "Executar" for b in at.button)
    assert all(c.value for c in at.checkbox)  # todas marcadas por padrão


def test_executar_sem_aplicacao_mostra_erro():
    at = _app()
    for c in at.checkbox:
        c.uncheck()
    at.button(key="ca_executar").click().run()
    assert not at.exception
    assert any("aplica" in e.value.lower() for e in at.error)


def test_executar_sem_credenciais_mostra_erro():
    at = _app()
    at.button(key="ca_executar").click().run()
    assert not at.exception
    assert any("login" in e.value.lower() for e in at.error)


def test_lista_invalida_mostra_erro():
    import io

    import openpyxl

    at = _app()
    wb = openpyxl.Workbook()
    wb.active.append(["coluna errada"])
    buf = io.BytesIO()
    wb.save(buf)
    at.file_uploader[0].upload("escolas.xlsx", buf.getvalue())
    at.text_input(key="ca_login").set_value("123")
    at.text_input(key="ca_senha").set_value("x")
    at.button(key="ca_executar").click().run()
    assert not at.exception
    assert at.error


def test_estado_concluido_mostra_tabela_e_pacote():
    from datetime import datetime

    from apps.coleta_automatica.src.runner import ResultadoEtapa

    at = _app()
    at.session_state["ca_running"] = False
    at.session_state["ca_finalized"] = True
    at.session_state["ca_inicio"] = datetime(2026, 10, 20, 21, 15, 3)
    at.session_state["ca_fim"] = datetime(2026, 10, 20, 21, 34, 50)
    at.session_state["ca_estado"] = {
        "resultados": [
            ResultadoEtapa(
                chave="gestor",
                titulo="Cadastro do gestor",
                situacao="concluida",
                segundos=48.0,
                caminho_artefato=None,
                caminho_pendencias=None,
                motivo=None,
            ),
        ],
        "etapa_atual": None,
        "shared_etapa": None,
        "aguardando": None,
        "interrompida": False,
        "pacote": None,
        "etapas_selecionadas": ["gestor"],
    }
    at.run()
    assert not at.exception
    assert any("Tempo de execução" in m.value for m in at.markdown)
    assert any("Cadastro do gestor" in m.value for m in at.markdown)


def test_estado_interrompido_avisa_que_nao_ha_pacote():
    at = _app()
    at.session_state["ca_running"] = False
    at.session_state["ca_finalized"] = True
    at.session_state["ca_estado"] = {
        "resultados": [],
        "etapa_atual": None,
        "shared_etapa": None,
        "aguardando": None,
        "interrompida": True,
        "pacote": None,
    }
    at.run()
    assert not at.exception
    assert any("interrompida" in m.value.lower() for m in at.markdown)


def test_nova_rodada_apaga_a_pasta_da_rodada_anterior(tmp_path):
    """A pasta da rodada guarda PII (relatórios, recibos): ela é apagada."""
    pasta = tmp_path / "coleta_automatica_tmp_teste"
    pasta.mkdir()
    (pasta / "relatorio_alunos.zip").write_bytes(b"dados")

    at = _app()
    at.session_state["ca_running"] = False
    at.session_state["ca_finalized"] = True
    at.session_state["ca_pasta"] = str(pasta)
    at.run()
    at.button(key="ca_nova_rodada").click().run()

    assert not at.exception
    assert not pasta.exists(), "a pasta da rodada anterior ficou no disco"
