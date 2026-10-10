import sys
from pathlib import Path

import streamlit as st
import base64
from PIL import Image
from apps.inicio.inicio import show_home_page

# ---------------------------------------------------------------------------
# Registro da aplicação "COLETA DE DADOS CADASTRAIS DAS ESCOLAS" como pacote importável (src)
# ---------------------------------------------------------------------------
_WEB_SCRAPING_PATH = Path(__file__).resolve().parent / "apps" / "coleta_cadastros_escolas"
if str(_WEB_SCRAPING_PATH) not in sys.path:
    sys.path.insert(0, str(_WEB_SCRAPING_PATH))

from src.frontend import render_frontend

from apps.coleta_gestor.src.frontend import render_gestor_frontend

from apps.coleta_relatorios.src.frontend import render_report_frontend
from apps.coleta_relatorios.src.reports import REPORTS

from apps.coleta_recibos_fechamento.src.frontend import render_receipt_frontend

from apps.verificacao_inconsistencias.src.frontend import render_validation_frontend

from apps.verificacao_inconsistencias.src.validations import VALIDATIONS

# Adequação de Relatórios
from apps.adequacao_turmas.src.frontend import render_adequacao_turmas_frontend

from apps.adequacao_alunos.src.frontend import render_adequacao_alunos_frontend

from apps.adequacao_profissionais.src.frontend import render_adequacao_profissionais_frontend

# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------
def get_base64_image(image_path):
    """Codifica imagem em Base64 para uso inline no HTML."""
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode("utf-8")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Rodapé padrão (autoria) — exibido em todas as telas
# ---------------------------------------------------------------------------
FOOTER_HTML = """
<div style="text-align:center; margin-top:3rem; color:var(--text-secondary);
            font-size:0.82rem; border-top:1px solid var(--border-default); padding-top:1rem;">
    Desenvolvido por Rodrigo Nunes - 2026
</div>
"""


def render_license_footer():
    """Exibe o rodapé com a autoria da aplicação."""
    st.markdown(FOOTER_HTML, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Configuração da página
# ---------------------------------------------------------------------------
try:
    page_icon_img = Image.open("imagem/image.png")
except Exception:
    page_icon_img = "🏫"

st.set_page_config(
    page_title="APLICAÇÕES DE APOIO - CENSO ESCOLAR",
    page_icon=page_icon_img,
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------------------------------------------------------------
# CSS Global — Tema Azul
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    /* Manter o tema escuro e remover o menu de configurações do Streamlit. */
    [data-testid="stMainMenu"],
    #MainMenu {
        display: none !important;
    }

    /* ── Sidebar recolhível pelo usuário (botão nativo do Streamlit) ── */
    /* Largura fixa quando expandida (a animação de colapso fica a cargo do Streamlit) */
    section[data-testid="stSidebar"][aria-expanded="true"] {
        min-width: 280px !important;
        max-width: 280px !important;
        width: 280px !important;
    }


    /* ── Variáveis de design (Tokens) ── */
    :root {
        --bg-general: #131722;
        --bg-card: #1e222d;
        --bg-sidebar: #171b26;

        --border-default: #2a2e39;
        --border-subtle: rgba(255, 255, 255, 0.07);

        --text-primary: #ffffff;
        --text-secondary: #b2b5be;
        --text-muted: rgba(232, 229, 222, 0.35);

        /* Status (20% opacidade no fundo) */
        --status-ok: #22c55e;
        --status-ok-bg: rgba(34, 197, 94, 0.2);
        --status-warning: #eab308;
        --status-warning-bg: rgba(234, 179, 8, 0.2);
        --status-danger: #ef4444;
        --status-danger-bg: rgba(239, 68, 68, 0.2);
        --status-info: #3b82f6;
        --status-info-bg: rgba(59, 130, 246, 0.2);

        /* Arredondamento */
        --radius-sm: 6px;
        --radius-md: 8px;
        --radius-lg: 12px;
    }

    /* ── Base — fonte e cor padrão de todo o conteúdo ── */
    html, body, [class*="css"], .stText, .stMarkdown,
    p, span, div, label, input, button, select {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif !important;
    }
    /* Preserva a fonte dos ícones Material (ex.: botão de recolher a sidebar) */
    span[data-testid="stIconMaterial"] {
        font-family: 'Material Symbols Rounded' !important;
    }

    /* Cor padrão do texto e fundo da área principal */
    .stApp {
        background-color: var(--bg-general) !important;
        overflow: auto !important;
    }
    .stApp, .stApp * {
        color: var(--text-primary);
    }

    /* Scroll normal em todas as telas (necessário para exibir o rodapé) */
    html, body {
        overflow: auto !important;
    }

    /* Container Principal */
    .stMainBlockContainer, [data-testid="stAppViewBlockContainer"] {
        max-width: 1400px !important;
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
        margin: 0 auto !important;
    }

    /* Markdown — parágrafos, listas e texto em geral */
    .stMarkdown p,
    .stMarkdown li,
    .stMarkdown ul,
    .stMarkdown ol,
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li,
    [data-testid="stMarkdownContainer"] span {
        color: #d0d3db !important;
        font-size: 0.92rem !important;
        line-height: 1.65 !important;
    }

    /* Negrito dentro do markdown */
    .stMarkdown strong, [data-testid="stMarkdownContainer"] strong {
        color: #ffffff !important;
        font-weight: 700 !important;
    }

    /* Links — neutralizar o azul padrão do Streamlit */
    .stMarkdown a, [data-testid="stMarkdownContainer"] a {
        color: #93c5fd !important;
        text-decoration: none !important;
    }

    /* ── Tipografia e Hierarquia ── */
    h1, .stMarkdown h1 {
        font-size: 1.95rem !important;
        font-weight: 600 !important;
        color: #ffffff !important;
    }
    h2, .stMarkdown h2 {
        font-size: 1.15rem !important;
        font-weight: 600 !important;
        color: #ffffff !important;
    }
    h3, .stMarkdown h3 {
        font-size: 1.0rem !important;
        font-weight: 600 !important;
        color: #ffffff !important;
    }

    /* Subheaders do Streamlit (st.subheader) */
    [data-testid="stHeadingWithActionElements"] h2,
    [data-testid="stHeadingWithActionElements"] h3 {
        font-size: 1.0rem !important;
        font-weight: 600 !important;
        color: #ffffff !important;
        margin-bottom: 0.6rem !important;
    }

    /* Rótulos/Labels */
    label, .stWidgetLabel p, [data-testid="stWidgetLabel"] p,
    [data-testid="stWidgetLabel"] label, .stWidgetLabel label {
        text-transform: uppercase !important;
        font-size: 0.78rem !important;
        font-weight: 700 !important;
        color: #d0d3db !important;
        letter-spacing: 0.6px !important;
    }

    /* Texto dentro dos inputs — garantir visibilidade */
    .stTextInput input, .stTextArea textarea, .stNumberInput input {
        color: #ffffff !important;
        font-size: 0.95rem !important;
        font-weight: 400 !important;
    }
    .stTextInput input::placeholder, .stTextArea textarea::placeholder,
    .stNumberInput input::placeholder {
        color: rgba(178, 181, 190, 0.6) !important;
    }
    /* Baseweb input text */
    [data-baseweb="input"] input {
        background-color: var(--bg-card) !important;
        color: #ffffff !important;
        font-size: 0.95rem !important;
    }
    [data-baseweb="input"] input::placeholder {
        color: rgba(178, 181, 190, 0.6) !important;
    }

    /* ── Ocultar barras/toolbars de colunas (Streamlit interno) ── */
    [data-testid="stElementToolbar"],
    [data-testid="stElementToolbarButton"] {
        display: none !important;
    }
    /* Remover overflow/barras fantasma nos blocos horizontais */
    [data-testid="stHorizontalBlock"] {
        gap: 1rem !important;
        overflow: visible !important;
    }

    /* ── BARRAS FANTASMA: ocultar containers que envolvem apenas
          o <div class="custom-card"> de abertura (sem conteúdo real)  ── */
    /* Alveja o stMarkdownContainer cujo único filho é .custom-card vazio */
    [data-testid="stMarkdownContainer"]:has(> .custom-card:empty) {
        display: none !important;
        height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    /* Sobe um nível: stMarkdown que contém o container problemático */
    [data-testid="stMarkdown"]:has([data-testid="stMarkdownContainer"] > .custom-card:empty) {
        display: none !important;
        height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    /* Sobe mais um nível: stElementContainer pai */
    [data-testid="stElementContainer"]:has([data-testid="stMarkdownContainer"] > .custom-card:empty) {
        display: none !important;
        height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
    }

    /* Fallback: qualquer elemento vazio criado pelo Streamlit */
    .stElementContainer:empty,
    [data-testid="stVerticalBlock"] > div:empty {
        display: none !important;
    }

    /* Focus */
    input:focus, select:focus, textarea:focus, button:focus, [data-baseweb="input"] input:focus {
        outline: 3px solid #3b82f6 !important;
        outline-offset: 2px !important;
        border-color: #3b82f6 !important;
        box-shadow: none !important;
    }

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] {
        background-color: var(--bg-sidebar) !important;
        border-right: 1px solid var(--border-default) !important;
    }
    section[data-testid="stSidebar"] * {
        color: var(--text-secondary) !important;
    }

    /* ── Menu de Navegação (st.radio na Sidebar) ── */
    section[data-testid="stSidebar"] div[data-testid="stRadio"] [role="radiogroup"] > label {
        background-color: transparent !important;
        border: none !important;
        border-left: 3px solid transparent !important;
        color: var(--text-secondary) !important;
        font-weight: 500 !important;
        font-size: 0.80rem !important;
        padding: 8px 12px !important;
        margin-bottom: 4px !important;
        border-radius: 0px !important;
        transition: all 0.2s ease !important;
        cursor: pointer !important;
        display: flex !important;
        align-items: center !important;
    }
    /* Hover */
    section[data-testid="stSidebar"] div[data-testid="stRadio"] [role="radiogroup"] > label:hover {
        background-color: rgba(255, 255, 255, 0.08) !important;
        color: var(--text-primary) !important;
    }
    /* Ativo (Streamlit input selecionado) */
    section[data-testid="stSidebar"] div[data-testid="stRadio"] [role="radiogroup"] > label:has(input:checked) {
        background-color: rgba(59, 130, 246, 0.08) !important;
        border-left: 3px solid #3b82f6 !important;
        color: #f0f0f0 !important;
    }
    /* Ocultar círculo de seleção original */
    section[data-testid="stSidebar"] div[data-testid="stRadio"] [role="radiogroup"] > label > div:first-child {
        display: none !important;
    }

    /* ── Banner / Title container ── */
    .title-container {
        background-color: var(--bg-card) !important;
        border: 1px solid var(--border-default) !important;
        padding: 2.5rem !important;
        border-radius: var(--radius-lg) !important;
        color: var(--text-primary) !important;
        margin-bottom: 2rem !important;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4) !important;
        animation: fadeIn 0.7s ease-out !important;
    }
    .title-container h1 {
        color: var(--text-primary) !important;
        font-weight: 600 !important;
        font-size: 1.95rem !important;
        margin: 0 0 0.4rem 0 !important;
    }
    .title-container p {
        color: var(--text-secondary) !important;
        font-size: 1.05rem !important;
        margin: 0 !important;
        font-weight: 400 !important;
    }

    /* ── Cards ── */
    .custom-card {
        background-color: var(--bg-card) !important;
        border-radius: var(--radius-md) !important;
        padding: 16px 18px !important;
        border: 1px solid var(--border-default) !important;
        margin-bottom: 1.5rem !important;
        transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2) !important;
    }
    .custom-card:hover {
        border-color: rgba(255, 255, 255, 0.12) !important;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4) !important;
        transform: none !important;
    }

    /* ── Botões Streamlit ── */
    .stButton > button, .stDownloadButton > button {
        background: transparent !important;
        color: var(--text-primary) !important;
        border: 1px solid #454955 !important;
        border-radius: var(--radius-sm) !important;
        font-weight: 600 !important;
        padding: 0.5rem 1.2rem !important;
        transition: all 0.2s ease !important;
        box-shadow: none !important;
    }
    .stButton > button:hover {
        background-color: rgba(255, 255, 255, 0.05) !important;
        border-color: var(--text-primary) !important;
    }
    /* Botão de sucesso (Download) */
    .stDownloadButton > button {
        border: 1px solid var(--status-ok) !important;
        color: var(--status-ok) !important;
    }
    .stDownloadButton > button:hover {
        background-color: var(--status-ok-bg) !important;
        color: var(--text-primary) !important;
        border-color: var(--status-ok) !important;
    }

    /* ── Inputs e Dropdowns ── */
    .stTextInput input, .stSelectbox select, .stTextArea textarea, .stNumberInput input {
        background-color: #1e222d !important;
        color: #ffffff !important;
        border: 1px solid var(--border-default) !important;
        border-radius: var(--radius-sm) !important;
        font-size: 0.95rem !important;
    }
    /* Estilização específica do select do Streamlit (Base Web UI) */
    div[data-baseweb="select"] > div {
        background-color: var(--bg-card) !important;
        color: var(--text-primary) !important;
        border: 1px solid var(--border-default) !important;
        border-radius: var(--radius-sm) !important;
        min-height: 28px !important;
        height: 28px !important;
    }
    div[data-baseweb="select"] [data-testid="stSelectboxVirtualFocus"] {
        padding-top: 0 !important;
        padding-bottom: 0 !important;
    }

    /* Pills/Tags de Filtro (Multiselect tags) */
    [data-baseweb="tag"] {
        border-radius: 12px !important;
        background-color: var(--border-subtle) !important;
        color: var(--text-secondary) !important;
        border: 1px solid transparent !important;
    }
    [data-baseweb="tag"]:active, [data-baseweb="tag"]:focus {
        border-color: #3b82f6 !important;
        background-color: rgba(59, 130, 246, 0.12) !important;
        color: #93c5fd !important;
    }

    /* ── Métricas (KPIs) ── */
    [data-testid="stMetricLabel"] {
        text-transform: uppercase !important;
        font-size: 0.7rem !important;
        font-weight: 600 !important;
        color: var(--text-secondary) !important;
    }
    [data-testid="stMetricValue"] {
        color: var(--text-primary) !important;
        font-weight: 700 !important;
        font-size: 1.65rem !important;
    }
    /* Delta colors */
    [data-testid="stMetricDelta"] {
        font-weight: 600 !important;
    }

    /* ── Painéis / Expanders ── */
    div[data-testid="stExpander"] {
        border: 1px solid var(--border-default) !important;
        border-radius: var(--radius-md) !important;
        background-color: var(--bg-card) !important;
    }
    div[data-testid="stExpander"] details summary {
        padding: 14px 18px 12px !important;
        border-bottom: 1px solid var(--border-subtle) !important;
        color: var(--text-primary) !important;
        font-weight: 600 !important;
    }
    div[data-testid="stExpander"] details [role="region"] {
        padding: 16px 18px !important;
    }

    /* Tooltips */
    [data-testid="stTooltipIcon"] {
        width: 16px !important;
        height: 16px !important;
        cursor: help !important;
    }
    div[data-testid="stTooltipContent"] {
        background-color: var(--bg-card) !important;
        color: var(--text-primary) !important;
        border: 1px solid var(--border-default) !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4) !important;
    }

    /* ── Tabelas ── */
    table {
        border-collapse: separate !important;
        border-spacing: 0 !important;
        width: 100% !important;
        border: 1px solid var(--border-default) !important;
        border-radius: var(--radius-md) !important;
        overflow: hidden !important;
        background-color: var(--bg-card) !important;
    }
    th {
        background-color: rgba(255, 255, 255, 0.03) !important;
        color: var(--text-primary) !important;
        font-weight: 600 !important;
        padding: 10px 12px !important;
        border-bottom: 1px solid var(--border-default) !important;
    }
    td {
        padding: 10px 12px !important;
        border-bottom: 1px solid var(--border-subtle) !important;
        color: var(--text-secondary) !important;
        max-width: 250px !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        white-space: nowrap !important;
    }
    tr:last-child td {
        border-bottom: none !important;
    }
    tr:hover td {
        background-color: rgba(255, 255, 255, 0.02) !important;
    }

    /* Badges */
    .badge {
        display: inline-flex !important;
        align-items: center !important;
        padding: 3px 7px !important;
        border-radius: 4px !important;
        font-weight: 600 !important;
        font-size: 0.75rem !important;
    }
    .badge-ok {
        background-color: var(--status-ok-bg) !important;
        color: var(--status-ok) !important;
    }
    .badge-warning {
        background-color: var(--status-warning-bg) !important;
        color: var(--status-warning) !important;
    }
    .badge-danger {
        background-color: var(--status-danger-bg) !important;
        color: var(--status-danger) !important;
    }
    .badge-info {
        background-color: var(--status-info-bg) !important;
        color: var(--status-info) !important;
    }

    /* Banners de Alerta */
    div[data-testid="stAlert"] {
        background-color: rgba(234, 179, 8, 0.07) !important;
        border: 1px solid var(--status-warning) !important;
        color: #a16207 !important;
        border-radius: var(--radius-sm) !important;
    }

    /* ── Remove o ícone redundante na dropzone do file_uploader ──
       (o texto "Upload" já comunica a ação; o ícone era duplicado) */
    [data-testid="stFileUploaderDropzone"] [data-testid="stIconMaterial"] {
        display: none !important;
    }

    /* ── Animação ── */
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(12px); }
        to   { opacity: 1; transform: translateY(0); }
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
logo_base64 = get_base64_image("imagem/image.png")

if logo_base64:
    st.sidebar.markdown(f"""
    <div style="text-align:center; padding: 16px 8px 20px 8px;">
        <img src="data:image/png;base64,{logo_base64}"
             style="width:96px; height:96px; border-radius:16px;
                    box-shadow: 0 6px 18px rgba(0,0,0,0.25);
                    background:#fff; padding:5px; margin-bottom:10px;" />
        <h4 style="margin:0; color:#ffffff; font-weight:700; font-size:1.1rem;">APLICAÇÕES DE APOIO
        CENSO ESCOLAR</h4>
    </div>
    """, unsafe_allow_html=True)
else:
    st.sidebar.markdown("""
    <div style="text-align:center; margin-bottom:1.5rem;">
        <h3 style="color:#ffffff; font-weight:700;">SEDUCT</h3>
        
    </div>
    """, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Menu lateral: item raiz "Tela Inicial" + grupos colapsáveis (expander) com
# submenus (botões). Seleção única global via session_state["nav_page"].
# ---------------------------------------------------------------------------
st.markdown("""
<style>
/* Botões de navegação do sidebar com aparência de item de menu */
[data-testid="stSidebar"] [data-testid="stButton"] button {
    width: 100%;
    justify-content: flex-start;
    text-align: left;
    border: none;
    background: transparent;
    color: #d1d4dc;
    font-weight: 500;
    padding: 0.4rem 0.6rem;
    border-radius: 8px;
}
[data-testid="stSidebar"] [data-testid="stButton"] button:hover {
    background: rgba(255,255,255,0.06);
    color: #ffffff;
}
[data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"] {
    background: var(--status-info, #3b82f6);
    color: #ffffff;
}
</style>
""", unsafe_allow_html=True)

_MENU_GROUPS = {
    "Coleta do Educacenso": [
        "Dados Cadastrais da Unidades",
        "Dados dos Gestores Escolares",
        "Relatórios de Turmas",
        "Relatórios de Alunos",
        "Relatórios de Profissionais Escolares",
        "Recibos de Fechamento (1ª Etapa)",
    ],
    "Adequação de Relatórios": [
        "Adequação de Relatório de Turmas",
        "Adequação de Relatórios de Alunos",
        "Adequação de Relatórios de Profissionais",
    ],
    "Geração de Relatórios Gerais e de Inconsistências": [
        "Cadastro de Unidades",
        "Cadastro de Gestor",
        "Cadastro de Turmas",
        "Cadastro de Aluno",
        "Cadastro de Profissionais Escolares",
    ],
}

if "nav_page" not in st.session_state:
    st.session_state["nav_page"] = "Tela Inicial"


def _nav_item(container, label, key):
    active = st.session_state["nav_page"] == label
    if container.button(
        label, key=key, use_container_width=True,
        type="primary" if active else "secondary",
    ):
        st.session_state["nav_page"] = label
        st.rerun()


# Item raiz (sem grupo)
_nav_item(st.sidebar, "Tela Inicial", "nav_home")

# Grupos colapsáveis (expande o grupo que contém a página ativa)
for _grupo, _itens in _MENU_GROUPS.items():
    _exp = st.sidebar.expander(_grupo, expanded=st.session_state["nav_page"] in _itens)
    for _i, _label in enumerate(_itens):
        _nav_item(_exp, _label, f"nav_{_grupo}_{_i}")

page = st.session_state["nav_page"]

# ── Limpeza de estado ao trocar de página ─────────────────────────────
if "prev_nav_page" not in st.session_state:
    st.session_state["prev_nav_page"] = page
if st.session_state["prev_nav_page"] != page:
    keep = {"nav_page", "prev_nav_page"}
    for k in list(st.session_state.keys()):
        if k not in keep:
            del st.session_state[k]
    st.session_state["prev_nav_page"] = page

# ---------------------------------------------------------------------------
# Roteamento de páginas
# ---------------------------------------------------------------------------
if page == "Tela Inicial":
    # Home: hero centralizado com rodapé fixo (scroll via CSS global)
    show_home_page(logo_base64)
    render_license_footer()
elif page == "Dados Cadastrais da Unidades":
    render_frontend(logo_base64)
    render_license_footer()
elif page == "Dados dos Gestores Escolares":
    render_gestor_frontend(logo_base64)
    render_license_footer()
elif page in ("Relatórios de Turmas", "Relatórios de Alunos", "Relatórios de Profissionais Escolares"):
    _report_key = {
        "Relatórios de Turmas": "turmas",
        "Relatórios de Alunos": "alunos",
        "Relatórios de Profissionais Escolares": "profissionais",
    }[page]
    render_report_frontend(REPORTS[_report_key], logo_base64)
    render_license_footer()
elif page == "Recibos de Fechamento (1ª Etapa)":
    render_receipt_frontend(logo_base64)
    render_license_footer()
elif page in ("Adequação de Relatório de Turmas", "Adequação de Relatórios de Alunos", "Adequação de Relatórios de Profissionais"):
    _adeq_key = {
        "Adequação de Relatório de Turmas": "turmas",
        "Adequação de Relatórios de Alunos": "alunos",
        "Adequação de Relatórios de Profissionais": "profissionais",
    }[page]
    _adeq_func = {
        "turmas": render_adequacao_turmas_frontend,
        "alunos": render_adequacao_alunos_frontend,
        "profissionais": render_adequacao_profissionais_frontend,
    }[_adeq_key]
    _adeq_func(logo_base64)
    render_license_footer()
elif page in ("Cadastro de Unidades", "Cadastro de Gestor", "Cadastro de Turmas",
              "Cadastro de Aluno", "Cadastro de Profissionais Escolares"):
    _val_key = {
        "Cadastro de Unidades": "unidades",
        "Cadastro de Gestor": "gestor",
        "Cadastro de Turmas": "turmas",
        "Cadastro de Aluno": "aluno",
        "Cadastro de Profissionais Escolares": "profissionais",
    }[page]
    render_validation_frontend(VALIDATIONS[_val_key], logo_base64)
    render_license_footer()
