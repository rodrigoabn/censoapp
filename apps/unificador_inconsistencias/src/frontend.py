from __future__ import annotations

import hashlib

import streamlit as st

from .processor import build_school_reports_zip, output_filename
from .statistics_pdf import build_statistics_pdf, statistics_pdf_filename


_RELATORIOS = (
    ("escolas_ativas", "Relação de Escolas Ativas no Censo"),
    ("unidades", "Inconsistências de Unidades"),
    ("gestores", "Inconsistências de Gestores"),
    ("turmas", "Inconsistências de Turmas"),
    ("alunos", "Inconsistências de Alunos"),
    ("professores", "Inconsistências de Professores"),
)


def render_unificador_inconsistencias_frontend(
    logo_base64: str | None = None,
) -> None:
    if logo_base64:
        st.markdown(
            f"""
            <div class="title-container" style="display:flex; align-items:center; gap:1.5rem;">
                <img src="data:image/png;base64,{logo_base64}"
                     style="width:68px; height:68px; border-radius:12px;
                            box-shadow:0 4px 12px rgba(0,0,0,0.2);
                            background:#fff; padding:5px;" />
                <div>
                    <h1 style="margin:0; padding:0; line-height:1.2; color:white !important;">
                        Unificador de Inconsistências por Unidade Escolar
                    </h1>
                    <p style="margin-top:0.3rem; color:#bfdbfe; font-size:1rem; margin-bottom:0;">
                        Carregue os relatórios que serão utilizados na unificação.
                    </p>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div class="title-container">
                <h1>Unificador de Inconsistências por Unidade Escolar</h1>
                <p>Carregue os relatórios que serão utilizados na unificação.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    uploaded_reports: dict[str, bytes | None] = {}
    ignored_reports: set[str] = set()
    active_schools_bytes: bytes | None = None
    input_signature = hashlib.sha256()

    for start in range(0, len(_RELATORIOS), 2):
        columns = st.columns(2)
        for column, (key, label) in zip(columns, _RELATORIOS[start : start + 2]):
            with column:
                st.markdown('<div class="custom-card">', unsafe_allow_html=True)
                st.markdown(f"**{label}**")
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
                st.markdown("</div>", unsafe_allow_html=True)

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

    if st.button(
        "Gerar arquivos XLSX por unidade escolar",
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
        if st.session_state.get("unificador_escolas_ativas_ignorar", False):
            st.error("A Relação de Escolas Ativas no Censo é obrigatória e não pode ser ignorada.")
        elif active_schools_bytes is None:
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
                    st.session_state["unificador_stats_pdf_bytes"] = build_statistics_pdf(stats)
                    st.session_state["unificador_stats_pdf_filename"] = statistics_pdf_filename()
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

    with st.expander("Orientações de uso"):
        st.markdown(
            """
            1. Envie a **Relação de Escolas Ativas no Censo**, com o código INEP na primeira coluna e o nome da unidade na segunda.
            2. Envie cada relatório de inconsistências XLS ou XLSX ou marque **Não usar este relatório**.
            3. Clique em **Gerar arquivos XLSX por unidade escolar**. Será criado um ZIP com um arquivo XLSX para cada escola ativa.
            4. Cada arquivo conterá as abas Cadastro da Unidade, Gestores, Turmas, Alunos e Professores.
            """
        )
