from __future__ import annotations

import streamlit as st


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
                    st.file_uploader(
                        f"Arquivo XLS ou XLSX — {label}",
                        type=["xls", "xlsx"],
                        key=f"unificador_{key}_arquivo",
                        label_visibility="collapsed",
                    )
                st.markdown("</div>", unsafe_allow_html=True)

    with st.expander("Orientações de uso"):
        st.markdown(
            """
            1. Envie os relatórios XLS ou XLSX que deseja utilizar.
            2. Marque **Não usar este relatório** para cada relatório que não será incluído.
            3. As regras de unificação serão definidas posteriormente.
            """
        )
