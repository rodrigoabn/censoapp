from __future__ import annotations

from datetime import datetime

import streamlit as st

from apps.common.banner import banner_titulo
from apps.common.orientacoes import COLS_ORIENTACOES, card_orientacoes

from .processor import adequar_profissionais
from .upload import read_zip_csvs, write_zip_from_dataframes


def _output_filename(config: dict, suffix: str = "adequado", ext: str = "zip") -> str:
    data_str = datetime.now().strftime("%d-%m-%Y")
    return f"{suffix}_{config['key']}_{data_str}.{ext}"


def render_adequacao_profissionais_frontend(logo_base64: str | None = None) -> None:
    """Tela de adequação de Relatórios de Profissionais Escolares.

    Layout idêntico às outras aplicações do HUB.
    """

    # ── Banner (tema HUB) ──
    banner_titulo(
        st,
        "Adequação de Relatórios de Profissionais Escolares",
        "Converte o ZIP de profissionais exportado do Educacenso para o layout padronizado.",
        logo_base64,
    )

    # ── Formulário (coluna principal) + Orientações (coluna direita) ──
    col_form, col_help = st.columns(COLS_ORIENTACOES)

    with col_form:
        st.markdown('<div class="custom-card">', unsafe_allow_html=True)
        with st.form("adequacao_profissionais_form"):
            arquivo = st.file_uploader(
                "Arquivo ZIP com CSVs de profissionais",
                type=["zip"],
                help="ZIP contendo os CSVs exportados do Educacenso (um por escola).",
            )
            submitted = st.form_submit_button("Executar")
        st.markdown('</div>', unsafe_allow_html=True)

    with col_help:
        card_orientacoes(
            st,
            corpo="""
            1. Envie o arquivo ZIP com os CSVs exportados do Educacenso (relação profissional-escola).
            2. Clique em **Executar**: o sistema lerá os CSVs e aplicará as regras de adequação.
            3. Após o processamento, o botão **Baixar ZIP Adequado** ficará disponível.
            4. O ZIP resultante contém os mesmos CSVs porém com as correções aplicadas.
            5. O arquivo pode ser uploadado posteriormente na aplicação de **Verificação de Inconsistências no Cadastro de Profissionais Escolares**.
            """,
        )

    # ── Processamento ──
    if submitted and arquivo is not None:
        with st.spinner("Lendo e processando CSVs..."):
            # 1. Ler CSVs do ZIP
            csvs = read_zip_csvs(arquivo.read())

            if not csvs:
                st.error("Nenhum CSV encontrado no ZIP enviado.")
                return

            # 2. Aplicar regras de adequação (placeholder)
            df_adequado = adequar_profissionais(csvs)

            # 3. Contar quantidade
            n_escolas = len(df_adequado)
            n_registros = sum(len(df) for df in df_adequado.values())

            st.success(
                f"Processamento concluído. {n_escolas} escola(s), "
                f"{n_registros} registro(s) totais."
            )

            # 4. Gerar ZIP adequado
            zip_bytes = write_zip_from_dataframes(df_adequado)

            # 5. Botão de download
            st.download_button(
                label="Baixar ZIP Adequado",
                data=zip_bytes,
                file_name=_output_filename({"key": "profissionais"}),
                mime="application/zip",
                use_container_width=True,
            )
    elif submitted and arquivo is None:
        st.error("Por favor, envie o arquivo ZIP antes de processar.")