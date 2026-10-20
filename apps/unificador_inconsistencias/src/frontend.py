from __future__ import annotations

import hashlib

import streamlit as st

from apps.common.banner import banner_titulo
from apps.common.orientacoes import COLS_ORIENTACOES, card_orientacoes

from .processor import build_school_reports_zip, output_filename
from .statistics_pdf import build_statistics_pdf, statistics_pdf_filename

_RELATORIOS = (
    ("escolas_ativas", "Relação de Escolas Ativas no Censo", True),
    ("unidades", "Inconsistências de Unidades", False),
    ("gestores", "Inconsistências de Gestores", False),
    ("turmas", "Inconsistências de Turmas", False),
    ("alunos", "Inconsistências de Alunos", False),
    ("professores", "Inconsistências de Professores", False),
)


def render_unificador_inconsistencias_frontend(
    logo_base64: str | None = None,
) -> None:
    banner_titulo(
        st,
        "Unificador de Inconsistências por Unidade Escolar",
        "Carregue os relatórios que serão utilizados na unificação.",
        logo_base64,
    )

    uploaded_reports: dict[str, bytes | None] = {}
    ignored_reports: set[str] = set()
    active_schools_bytes: bytes | None = None
    input_signature = hashlib.sha256()

    st.markdown(
        """
        <style>
        /* Seletor específico: o CSS global do HUB aplica !important em
           span dentro de markdown e sobrescreveria a cor inline. */
        [data-testid="stMarkdownContainer"] span.unificador-obrigatorio {
            color: var(--status-danger) !important;
            font-weight: 700 !important;
            font-style: italic !important;
            font-size: 0.82rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    col_form, col_help = st.columns(COLS_ORIENTACOES)

    with col_form:
        for key, label, obrigatorio in _RELATORIOS:
            # Borda nativa do Streamlit — a mesma dos formulários das outras
            # aplicações do HUB (1px rgba(250,250,250,0.2), raio 8px).
            with st.container(border=True):
                if obrigatorio:
                    st.markdown(f"**{label}**")
                    st.markdown(
                        '<span class="unificador-obrigatorio">É obrigatório '
                        "informar a planilha com as escolas ativas a serem "
                        "unificadas.</span>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(f"**{label}**")
                if key == "escolas_ativas":
                    ignorar = False
                    uploaded_bytes = None
                    uploaded_file = None
                    uploaded_file = st.file_uploader(
                        f"Arquivo XLS ou XLSX — {label}",
                        type=["xls", "xlsx"],
                        key=f"unificador_{key}_arquivo",
                        label_visibility="collapsed",
                    )
                    if uploaded_file is not None:
                        uploaded_bytes = uploaded_file.getvalue()
                else:
                    ignorar = st.checkbox(
                        "Não usar este relatório",
                        key=f"unificador_{key}_ignorar",
                    )
                    uploaded_bytes = None
                    if ignorar:
                        st.markdown(
                            """
                            <div aria-disabled="true" style="
                                background-color: rgba(255, 255, 255, 0.04);
                                border: 1px solid rgba(255, 255, 255, 0.08);
                                border-radius: 0.5rem;
                                color: rgba(255, 255, 255, 0.45);
                                padding: 1rem;
                                text-align: center;
                            ">Upload desabilitado para este relatório</div>
                            """,
                            unsafe_allow_html=True,
                        )
                    else:
                        uploaded_file = st.file_uploader(
                            f"Arquivo XLS ou XLSX — {label}",
                            type=["xls", "xlsx"],
                            key=f"unificador_{key}_arquivo",
                            label_visibility="collapsed",
                        )
                        if uploaded_file is not None:
                            uploaded_bytes = uploaded_file.getvalue()

                input_signature.update(key.encode("utf-8"))
                input_signature.update(b"1" if ignorar else b"0")
                if uploaded_bytes is not None:
                    input_signature.update(uploaded_file.name.encode("utf-8"))
                    input_signature.update(uploaded_bytes)
                if key == "escolas_ativas":
                    active_schools_bytes = uploaded_bytes
                else:
                    report_key = key
                    uploaded_reports[report_key] = uploaded_bytes
                    if ignorar:
                        ignored_reports.add(report_key)

        current_signature = input_signature.hexdigest()
        if st.session_state.get("unificador_input_signature") != current_signature:
            st.session_state["unificador_input_signature"] = current_signature
            for key in (
                "unificador_zip_bytes",
                "unificador_zip_filename",
                "unificador_stats",
                "unificador_stats_pdf_bytes",
                "unificador_stats_pdf_filename",
            ):
                st.session_state.pop(key, None)

        # Área de ação — mesma borda dos formulários das outras aplicações.
        with st.container(border=True):
            if st.button(
                "Executar",
                type="primary",
                use_container_width=True,
            ):
                for key in (
                    "unificador_zip_bytes",
                    "unificador_zip_filename",
                    "unificador_stats",
                    "unificador_stats_pdf_bytes",
                    "unificador_stats_pdf_filename",
                ):
                    st.session_state.pop(key, None)
                if active_schools_bytes is None:
                    st.error("Envie a Relação de Escolas Ativas no Censo para continuar.")
                else:
                    with st.spinner("Gerando um arquivo XLSX para cada unidade escolar..."):
                        try:
                            result, stats = build_school_reports_zip(
                                active_schools_bytes,
                                uploaded_reports,
                                ignored_reports,
                            )
                        except ValueError as exc:
                            st.error(str(exc))
                        else:
                            st.session_state["unificador_zip_bytes"] = result
                            st.session_state["unificador_zip_filename"] = output_filename()
                            st.session_state["unificador_stats"] = stats
                            st.session_state["unificador_stats_pdf_bytes"] = (
                                build_statistics_pdf(stats)
                            )
                            st.session_state["unificador_stats_pdf_filename"] = (
                                statistics_pdf_filename()
                            )
                            st.success("Arquivos por unidade escolar gerados com sucesso.")

            zip_bytes = st.session_state.get("unificador_zip_bytes")
            if zip_bytes is not None:
                st.download_button(
                    "Baixar ZIP com arquivos por unidade escolar",
                    data=zip_bytes,
                    file_name=st.session_state["unificador_zip_filename"],
                    mime="application/zip",
                    use_container_width=True,
                )

            pdf_bytes = st.session_state.get("unificador_stats_pdf_bytes")
            if pdf_bytes is not None:
                st.download_button(
                    "Baixar relatório analítico de inconsistências (PDF)",
                    data=pdf_bytes,
                    file_name=st.session_state["unificador_stats_pdf_filename"],
                    mime="application/pdf",
                    use_container_width=True,
                )

    with col_help:
        card_orientacoes(
            st,
            corpo="""
            1. Envie a **Relação de Escolas Ativas no Censo**, com o código INEP na primeira coluna e o nome da unidade na segunda.
            2. Envie cada relatório de inconsistências XLS ou XLSX ou marque **Não usar este relatório**.
            3. Clique em **Executar**. Será criado um ZIP com um arquivo XLSX para cada escola ativa.
            4. Cada arquivo conterá as abas Cadastro da Unidade, Gestores, Turmas, Alunos e Professores.
            """,
        )
