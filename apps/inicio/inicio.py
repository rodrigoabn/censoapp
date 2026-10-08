from datetime import datetime

import streamlit as st

from apps.inicio.documentacao import build_documentacao_pdf


@st.cache_data(show_spinner=False)
def _documentacao_pdf_bytes(logo_base64: str | None) -> bytes:
    return build_documentacao_pdf(logo_base64)


def _documentacao_nome() -> str:
    data = datetime.now().strftime("%d-%m-%Y")
    return f"Documentacao_Aplicacoes_Apoio_Censo_Escolar_{data}.pdf"


def show_home_page(logo_base64):
    """Renderiza a tela inicial: hero centralizado com rodapé fixo embaixo."""

    # Remove o padding padrão do bloco principal só nesta página
    st.markdown("""
    <style>
        /* Zera padding do container principal para evitar scroll */
        .stMainBlockContainer, [data-testid="stAppViewBlockContainer"] {
            padding-top: 0 !important;
            padding-bottom: 0 !important;
        }
        .home-wrapper {
            display: flex;
            flex-direction: column;
            align-items: center;
            background-color: #131722;
            text-align: center;
            padding: 2rem 0;
            animation: fadeIn 0.8s ease-out;
        }
        /* Container principal vira coluna flexível na home, mantendo o
           rodapé (bloco separado) fixo na base da primeira tela */
        .stMainBlockContainer:has(.home-wrapper) {
            display: flex;
            flex-direction: column;
            min-height: 100vh;
        }
        .stMainBlockContainer:has(.home-wrapper) .home-wrapper {
            flex: 1 1 auto;
        }
        .home-hero {
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 1.8rem;
            padding-top: 5cm;
        }
        .home-wrapper img {
            max-width: 280px;
            width: 100%;
            height: auto;
            border-radius: 24px;
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
        }
        .home-wrapper .home-title {
            color: #ffffff;
            font-size: 1.5rem;
            font-weight: 700;
            letter-spacing: 1px;
            margin: 0;
            text-align: center;
        }
        .home-wrapper p {
            color: #b2b5be;
            font-size: 1.05rem;
            font-weight: 400;
            max-width: 420px;
            line-height: 1.7;
            margin: 0;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to   { opacity: 1; transform: translateY(0); }
        }
    </style>
    """, unsafe_allow_html=True)

    img_tag = (
        f'<img src="data:image/png;base64,{logo_base64}" alt="Logo SEDUCT" />'
        if logo_base64 else
        '<span style="font-size:5rem;">🏫</span>'
    )

    st.markdown(f"""
    <div class="home-wrapper">
        <div class="home-hero">
            {img_tag}
            <h1 class="home-title">APLICAÇÕES DE APOIO CENSO ESCOLAR</h1>
            <p>Navegue pelo menu lateral para acessar as aplicações.</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col_btn = st.columns(3)[1]
    with col_btn:
        with st.spinner("Gerando documentação..."):
            pdf_bytes = _documentacao_pdf_bytes(logo_base64)
        st.download_button(
            "Baixar Documentação Completa (PDF)",
            data=pdf_bytes,
            file_name=_documentacao_nome(),
            mime="application/pdf",
            use_container_width=True,
        )
