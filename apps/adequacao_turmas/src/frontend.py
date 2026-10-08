from __future__ import annotations

import io
from datetime import datetime

import streamlit as st

from .upload import read_zip_csvs, write_zip_from_dataframes
from .processor import adequar_turmas


def _output_filename(config: dict, suffix: str = "adequado", ext: str = "zip") -> str:
    data_str = datetime.now().strftime("%d-%m-%Y")
    return f"{suffix}_{config['key']}_{data_str}.{ext}"


def render_adequacao_turmas_frontend(logo_base64: str | None = None) -> None:
    """Tela de adequação de Relatório de Turmas.

    Layout idêntico às outras aplicações do HUB:
    - Banner centralizado
    - Upload do ZIP com CSVs
    - Processamento com spinner
    - Download do ZIP adequado
    """

    # ── Banner ──
    if logo_base64:
        st.markdown(f"""
        <div style="text-align:center; padding: 16px 8px 20px 8px;">
            <img src="data:image/png;base64,{logo_base64}"
                 style="width:64px; height:64px; border-radius:12px;
                        box-shadow:0 4px 12px rgba(0,0,0,0.2);
                        background:#fff; padding:5px;" />
            <h2 style="margin:0; color:#ffffff; font-weight:700;">Adequação de Relatório de Turmas</h2>
        </div>""", unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="text-align:center; margin-bottom:1.5rem;">
            <h2 style="color:#ffffff;">Adequação de Relatório de Turmas</h2>

        </div>""", unsafe_allow_html=True)

    # ── Formulário ──
    st.markdown('<div class="custom-card">', unsafe_allow_html=True)
    with st.form("adequacao_turmas_form"):
        arquivo = st.file_uploader(
            "Arquivo ZIP com CSVs de turmas",
            type=["zip"],
            help="ZIP contendo os CSVs exportados do Educacenso (um por escola).",
        )
        submitted = st.form_submit_button("Processar e Adequar", type="primary")
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Processamento ──
    if submitted and arquivo is not None:
        with st.spinner("Lendo e processando CSVs..."):
            # 1. Ler CSVs do ZIP
            csvs = read_zip_csvs(arquivo.read())

            if not csvs:
                st.error("Nenhum CSV encontrado no ZIP enviado.")
                return

            # 2. Aplicar regras de adequação (placeholder)
            df_adequado = adequar_turmas(csvs)

            # 3. Contar quantidade de escolas/registros
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
                file_name=_output_filename({"key": "turmas"}),
                mime="application/zip",
                use_container_width=True,
            )
    elif submitted and arquivo is None:
        st.error("Por favor, envie o arquivo ZIP antes de processar.")

    # ── Ajuda ──
    with st.expander("Orientações de uso"):
        st.markdown("""
        1. Envie o arquivo ZIP com os CSVs exportados do Educacenso (relação turma-escola).
        2. Clique em **Processar e Adequar**: o sistema lerá os CSVs e aplicará as regras de adequação.
        3. Após o processamento, o botão **Baixar ZIP Adequado** ficará disponível.
        4. O ZIP resultante contém os mesmos CSVs porém com as correções aplicadas.
        5. O arquivo pode ser uploadado posteriormente na aplicação de **Verificação de Inconsistências no Cadastro de Turmas**.
        """)