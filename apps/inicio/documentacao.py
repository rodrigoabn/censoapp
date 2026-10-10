"""Geração da documentação completa das Aplicações de Apoio - Censo Escolar em PDF.

O PDF é montado em tempo de execução com reportlab (Platypus), sem dependências
de sistema, e fica disponível para download na Tela Inicial.
"""

from __future__ import annotations

import base64
import io
from datetime import datetime

_FONTE = "Helvetica"
_FONTE_B = "Helvetica-Bold"
_AZUL = "#1d4ed8"
_AZUL_CLARO = "#3b82f6"
_CINZA = "#6b7280"
_CINZA_CLARO = "#f1f5f9"
_GRID = "#cbd5e1"
_VERDE = "#16a34a"
_VERMELHO = "#dc2626"
_AMARELO = "#d97706"


def _estilos(cores=None):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
    from reportlab.lib.styles import ParagraphStyle

    corpo = ParagraphStyle(
        "corpo", fontName=_FONTE, fontSize=9.5, leading=13.5,
        textColor=colors.HexColor("#1f2937"), alignment=TA_JUSTIFY,
        spaceAfter=6,
    )
    return {
        "h1": ParagraphStyle(
            "h1", fontName=_FONTE_B, fontSize=15, leading=18,
            textColor=colors.HexColor(_AZUL), spaceBefore=16, spaceAfter=7,
            keepWithNext=1,
        ),
        "h2": ParagraphStyle(
            "h2", fontName=_FONTE_B, fontSize=12.5, leading=15,
            textColor=colors.HexColor("#111827"), spaceBefore=12, spaceAfter=5,
            keepWithNext=1,
        ),
        "h3": ParagraphStyle(
            "h3", fontName=_FONTE_B, fontSize=10.5, leading=13,
            textColor=colors.HexColor(_AZUL_CLARO), spaceBefore=9, spaceAfter=4,
            keepWithNext=1,
        ),
        "corpo": corpo,
        "corpo_central": ParagraphStyle(
            "corpo_central", parent=corpo, alignment=TA_CENTER, spaceAfter=3,
        ),
        "item": ParagraphStyle(
            "item", fontName=_FONTE, fontSize=9.5, leading=13.5,
            textColor=colors.HexColor("#1f2937"), alignment=TA_LEFT,
            leftIndent=12, bulletIndent=2, spaceAfter=3,
        ),
        "cel_h": ParagraphStyle(
            "cel_h", fontName=_FONTE_B, fontSize=8.5, leading=10.5,
            textColor=colors.white, alignment=TA_LEFT,
        ),
        "cel": ParagraphStyle(
            "cel", fontName=_FONTE, fontSize=8.3, leading=10.5,
            textColor=colors.HexColor("#111827"), alignment=TA_LEFT,
        ),
        "cap_titulo": ParagraphStyle(
            "cap_titulo", fontName=_FONTE_B, fontSize=24, leading=28,
            textColor=colors.HexColor("#111827"), alignment=TA_CENTER, spaceAfter=10,
        ),
        "cap_sub": ParagraphStyle(
            "cap_sub", fontName=_FONTE, fontSize=13, leading=17,
            textColor=colors.HexColor(_AZUL_CLARO), alignment=TA_CENTER, spaceAfter=6,
        ),
        "cap_meta": ParagraphStyle(
            "cap_meta", fontName=_FONTE, fontSize=10.5, leading=15,
            textColor=colors.HexColor(_CINZA), alignment=TA_CENTER, spaceAfter=2,
        ),
        "toc_h1": ParagraphStyle(
            "toc_h1", fontName=_FONTE_B, fontSize=10.5, leading=14,
            textColor=colors.HexColor("#111827"),
        ),
        "toc_h2": ParagraphStyle(
            "toc_h2", fontName=_FONTE, fontSize=9.5, leading=13,
            textColor=colors.HexColor("#374151"), leftIndent=14,
        ),
        "toc_h3": ParagraphStyle(
            "toc_h3", fontName=_FONTE, fontSize=9, leading=12,
            textColor=colors.HexColor("#6b7280"), leftIndent=28,
        ),
        "nota": ParagraphStyle(
            "nota", fontName=_FONTE, fontSize=8.8, leading=12,
            textColor=colors.HexColor("#374151"), spaceAfter=6,
        ),
    }


def _par(story, estilo, texto):
    from reportlab.platypus import Paragraph

    story.append(Paragraph(texto, estilo))


def _bullets(story, estilo, itens):
    from reportlab.platypus import Paragraph

    for it in itens:
        story.append(Paragraph(f"&bull; {it}", estilo))


def _tabela(story, estilos, headers, rows, col_widths=None):
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, Table, TableStyle

    dados = [[Paragraph(f"<b>{h}</b>", estilos["cel_h"]) for h in headers]]
    for r in rows:
        dados.append([Paragraph(str(c) if c != "" else " ", estilos["cel"]) for c in r])

    if col_widths is not None:
        col_widths = [w * cm for w in col_widths]

    t = Table(dados, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(_AZUL)),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor(_GRID)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(_CINZA_CLARO)]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t)
    story.append(_esp(5))


def _esp(altura=8):
    from reportlab.platypus import Spacer

    return Spacer(1, altura)


def _rodape_pagina(canvas, doc):
    from reportlab.lib import colors
    from reportlab.lib.units import cm

    canvas.saveState()
    canvas.setFont(_FONTE, 7.5)
    canvas.setFillColor(colors.HexColor(_CINZA))
    canvas.drawCentredString(doc.pagesize[0] / 2.0, 1.1 * cm, f"Página {doc.page}")
    canvas.drawString(2 * cm, 1.1 * cm, "APLICAÇÕES DE APOIO - CENSO ESCOLAR")
    canvas.drawRightString(doc.pagesize[0] - 2 * cm, 1.1 * cm, "Documentação")
    canvas.restoreState()


class _DocTemplate(object):
    """Ajuda a manter o fluxo padrão do BaseDocTemplate com TOC."""

    def __init__(self, arquivo):
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate

        self.doc = BaseDocTemplate(
            arquivo,
            pagesize=A4,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=1.6 * cm,
            title="Aplicações de Apoio - Censo Escolar - Documentação",
            author="Rodrigo Nunes",
        )
        frame = Frame(
            self.doc.leftMargin,
            self.doc.bottomMargin,
            self.doc.width,
            self.doc.height,
            id="corpo",
        )
        self.doc.addPageTemplates([
            PageTemplate(id="capa", frames=[frame], onPage=lambda c, d: None),
            PageTemplate(id="corpo", frames=[frame], onPage=_rodape_pagina),
        ])

    def multi_build(self, story):
        self.doc.multiBuild(story)


def build_documentacao_pdf(logo_base64: str | None = None) -> bytes:
    """Gera e retorna os bytes do PDF da documentação completa."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Image,
        PageBreak,
        Paragraph,
    )
    from reportlab.platypus.tableofcontents import TableOfContents

    estilos = _estilos()
    buf = io.BytesIO()
    doc = _DocTemplate(buf)

    toc = TableOfContents()
    toc.levelStyles = [estilos["toc_h1"], estilos["toc_h2"], estilos["toc_h3"]]

    story = []

    # ------------------------------------------------------------------
    # CAPA
    # ------------------------------------------------------------------
    story.append(_esp(90))
    if logo_base64:
        try:
            img = Image(io.BytesIO(base64.b64decode(logo_base64)), width=3.2 * cm, height=3.2 * cm)
            img.hAlign = "CENTER"
            story.append(img)
            story.append(_esp(18))
        except Exception:
            pass
    _par(story, estilos["cap_titulo"], "APLICAÇÕES DE APOIO<br/>CENSO ESCOLAR")
    _par(story, estilos["cap_sub"], "Documentação Técnica e Manual do Usuário")
    story.append(_esp(10))
    _par(story, estilos["cap_meta"], f"Versão: 1.0")
    _par(story, estilos["cap_meta"], f"Data: {datetime.now().strftime('%d/%m/%Y')}")
    _par(story, estilos["cap_meta"], "Autor: Rodrigo Nunes")
    _par(story, estilos["cap_meta"], "Secretaria Municipal de Educação - Campos dos Goytacazes/RJ")
    story.append(_esp(40))
    _par(story, estilos["nota"],
         "Este documento descreve o HUB de aplicações de apoio ao Censo Escolar: as aplicações de "
         "coleta de dados cadastrais e de relatórios no Educacenso (modo leitura), as aplicações de "
         "verificação de possíveis inconsistências e todas as regras de validação implementadas.")
    story.append(PageBreak())

    # ------------------------------------------------------------------
    # SUMÁRIO
    # ------------------------------------------------------------------
    _par(story, estilos["h1"], "Sumário")
    story.append(toc)
    story.append(PageBreak())

    # ==================================================================
    # 1. VISÃO GERAL
    # ==================================================================
    _par(story, estilos["h1"], "1. Visão Geral do Sistema")
    _par(story, estilos["corpo"],
         "O projeto é um HUB de aplicações em Streamlit, gerenciado pelo gerenciador de ambientes "
         "Python <b>uv</b>. O menu lateral esquerdo dá acesso às aplicações, organizadas em três "
         "grupos: Coleta do Educacenso, Adequação de Relatórios e Geração de Relatórios Gerais e de Inconsistências. "
         "Além disso, a Tela Inicial disponibiliza esta documentação para download em PDF.")
    _par(story, estilos["corpo"],
         "Todas as aplicações de coleta operam em <b>modo leitura</b> sobre o Educacenso "
         "(nunca gravam ou alteram dados), utilizam Playwright em modo síncrono para automatizar o "
         "navegador e reaproveitam uma única sessão de login durante toda a coleta.")
    _tabela(story, estilos,
            ["Grupo", "Aplicação", "Finalidade"],
            [
                ["Tela Inicial", "Tela Inicial",
                 "Hero com a marca do projeto e botão para baixar esta documentação (PDF)."],
                ["Coleta do Educacenso", "Dados Cadastrais da Unidades",
                 "Raspa a ficha cadastral completa de cada escola do Educacenso e consolida em um XLSX de 6 abas."],
                ["Coleta do Educacenso", "Dados dos Gestores Escolares",
                 "Coleta o vínculo do gestor escolar (e as abas Identificação e Dados pessoais) em XLSX de 3 abas."],
                ["Coleta do Educacenso", "Relatórios de Turmas",
                 "Baixa o relatório CSV de relação turma-escola de cada escola e empacota em ZIP."],
                ["Coleta do Educacenso", "Relatórios de Alunos",
                 "Baixa o relatório CSV de relação aluno-escola de cada escola e empacota em ZIP."],
                ["Coleta do Educacenso", "Relatórios de Profissionais Escolares",
                 "Baixa o relatório CSV de relação profissional-escola de cada escola e empacota em ZIP."],
                ["Coleta do Educacenso", "Recibos de Fechamento (1ª Etapa)",
                 "Baixa o recibo de fechamento (PDF) de cada escola e empacota em ZIP."],
                ["Geração de Relatórios Gerais e de Inconsistências", "Cadastro de Unidades",
                 "Valida as 5 abas do cadastro da escola e gera relatório XLSX das inconsistências."],
                ["Geração de Relatórios Gerais e de Inconsistências", "Cadastro de Gestor",
                 "Valida as 3 abas do cadastro do gestor e gera relatório XLSX."],
                ["Geração de Relatórios Gerais e de Inconsistências", "Cadastro de Turmas",
                 "Valida a tabela de turmas (curricular e escolarização) e gera relatório XLSX."],
                ["Geração de Relatórios Gerais e de Inconsistências", "Cadastro de Aluno",
                 "Valida a tabela de alunos e gera relatório XLSX, além de relatórios de apoio."],
                ["Geração de Relatórios Gerais e de Inconsistências", "Cadastro de Profissionais Escolares",
                 "Valida a tabela de profissionais escolares e gera relatório XLSX."],
            ],
            col_widths=[3.4, 4.6, 9.0])

    # ==================================================================
    # 2. REQUISITOS
    # ==================================================================
    _par(story, estilos["h1"], "2. Requisitos do Sistema")
    _par(story, estilos["h2"], "2.1 Software")
    _bullets(story, estilos["item"], [
        "Python 3.13 ou superior;",
        "Gerenciador de pacotes e ambientes uv;",
        "Streamlit (>= 1.58);",
        "pandas (>= 3.0), openpyxl (>= 3.1);",
        "playwright (== 1.61) para automação do navegador;",
        "reportlab para geração desta documentação em PDF;",
        "Chromium, instalado automaticamente na primeira execução (ver seção 3.2).",
    ])
    _par(story, estilos["h2"], "2.2 Dependências de sistema para o Playwright")
    _par(story, estilos["corpo"],
         "O arquivo <b>packages.txt</b> relaciona as bibliotecas de sistema exigidas pelo Chromium "
         "em ambientes Linux (libnss3, libnspr4, entre outras). Em distribuições Linux utilize o "
         "gerenciador de pacotes para instalá-las antes da primeira execução.")
    _par(story, estilos["h2"], "2.3 Credenciais")
    _bullets(story, estilos["item"], [
        "Usuário e senha do Educacenso (CPF e senha), digitados na tela de cada aplicação de coleta;",
        "Nunca são persistidos em arquivo;",
        "Arquivo de credenciais opcional em apps/coleta_cadastros_escolas/docs/credenciais.json (gitignored);",
        "Segredos do Streamlit em .streamlit/secrets.toml (gitignored).",
    ])

    # ==================================================================
    # 3. INSTALAÇÃO E EXECUÇÃO
    # ==================================================================
    _par(story, estilos["h1"], "3. Instalação e Execução")
    _par(story, estilos["h2"], "3.1 Preparar o ambiente")
    _par(story, estilos["item"],
         "1. Clone o repositório; 2. execute <b>uv sync</b> (ou <b>uv add</b> das dependências) para "
         "criar o ambiente virtual .venv e instalar os pacotes.")
    _par(story, estilos["h2"], "3.2 Iniciar o HUB")
    _par(story, estilos["corpo"],
         "Execute o comando abaixo na raiz do projeto e acesse a URL indicada pelo Streamlit:")
    _par(story, estilos["corpo_central"], "<b>uv run streamlit run app.py</b>")
    _par(story, estilos["corpo"],
         "Na primeira execução de qualquer aplicação de coleta, o Chromium é instalado "
         "automaticamente (spinner \"Preparando navegador (primeira execução)...\").")
    _par(story, estilos["h2"], "3.3 Testes")
    _par(story, estilos["corpo"],
         "Os testes de segurança ficam em tests/security/ e são pulados por padrão. Para a auditoria "
         "ao vivo, defina a variável de ambiente SECURITY_LIVE=1 (ver seção 9).")

    # ==================================================================
    # 4. SEGURANÇA, LGPD E MODO LEITURA
    # ==================================================================
    _par(story, estilos["h1"], "4. Segurança, LGPD e Modo Leitura")
    _bullets(story, estilos["item"], [
        "<b>Modo leitura:</b> todos os módulos de autenticação definem READ_ONLY = True e contam com "
        "uma proteção adicional (_assert_read_only) que impede qualquer escrita de dados no Educacenso;",
        "<b>Login:</b> realizado via Keycloak (acesso.inep.gov.br) com CPF e senha, sempre de forma "
        "interativa e nunca gravado em disco;",
        "<b>Sessão única:</b> o login é feito uma única vez e a sessão é reutilizada em todas as "
        "escolas, com relogin automático caso a sessão expire;",
        "<b>Dados locais:</b> o software roda localmente; não coletamos, armazenamos ou acessamos "
        "dados de alunos ou escolas;",
        "<b>LGPD:</b> a entidade que opera o sistema é a única Controladora dos dados tratados e "
        "assume toda a responsabilidade pela segurança das informações;",
        "<b>Não intrusivo:</b> os testes não realizam fuzzing nem força bruta e geram pouquíssimas "
        "requisições.",
    ])

    # ==================================================================
    # 5. USO GERAL DO HUB
    # ==================================================================
    _par(story, estilos["h1"], "5. Uso Geral do HUB")
    _par(story, estilos["corpo"],
         "Ao abrir o HUB, o menu lateral apresenta o item Tela Inicial e os três grupos de aplicações. "
         "A seleção é única e, ao trocar de página, o estado anterior é limpo (mantendo apenas a "
         "navegação). O rodapé de todas as telas indica a autoria da aplicação.")
    _bullets(story, estilos["item"], [
        "Tela Inicial: centraliza a marca e o botão para baixar esta documentação em PDF;",
        "Aplicações de coleta: exigem login (CPF + senha) e um arquivo com a lista de escolas;",
        "Aplicações de verificação: exigem o arquivo de dados (XLSX ou ZIP) e geram relatório de inconsistências.",
    ])

    # ==================================================================
    # 6. COLETA DE DADOS
    # ==================================================================
    _par(story, estilos["h1"], "6. Aplicações de Coleta de Dados")
    _par(story, estilos["corpo"],
         "Todas as aplicações de coleta seguem o mesmo padrão: formulário com login e senha, upload "
         "de um arquivo XLSX/XLS com as colunas <b>código do inep</b> e <b>nome da unidade</b> "
         "(leitura tolerante a maiúsculas/minúsculas e a variações de nome), botão para iniciar a "
         "extração, monitor com barra de progresso e botão de interromper, e download do resultado. "
         "A coleta roda em uma thread separada (nunca toca a interface) e interrompe de forma segura.")

    # ------------------------------------------------------------------
    _par(story, estilos["h2"], "6.1 Dados Cadastrais das Unidades")
    _par(story, estilos["corpo"],
         "Raspa a ficha cadastral completa de cada escola (página /escola/cadastro/dados-cadastrais) "
         "em modo leitura e gera um único arquivo XLSX com 6 abas, espelhando o modelo "
         "docs/modelo_coleta.xlsx. Cabeçalhos correspondem aos rótulos da segunda linha do modelo e as "
         "larguras das colunas são ajustadas automaticamente.")
    _par(story, estilos["h3"], "Saída: XLSX único (cadastro_escola_educacenso_DD-MM-AAAA.xlsx)")
    _tabela(story, estilos,
            ["Aba", "Conteúdo"],
            [
                ["Vinculação institucional e Conv", "Vinculação institucional e convênios (14 colunas)."],
                ["Funcionamento e Identificação", "Situação de funcionamento, endereço e identificação (24 colunas)."],
                ["Estrutura física", "Estrutura física da escola (89 colunas)."],
                ["Equipamentos e recursos tecnoló", "Equipamentos e recursos tecnológicos (28 colunas)."],
                ["Recursos humanos", "Recursos humanos (21 colunas)."],
                ["Organização escolar", "Organização escolar (42 colunas)."],
            ],
            col_widths=[6.5, 10.5])
    _par(story, estilos["h3"], "Detalhes técnicos")
    _bullets(story, estilos["item"], [
        "Extrai campos por aba via JavaScript no navegador (mat-form-field, mat-checkbox, mat-radio-button);",
        "Aceita automaticamente o Termo de Sigilo quando apresentado;",
        "Arquivos temporários por aba em /tmp/educacenso_tmp (CSV utf-8) e consolidação final em XLSX;",
        "Exceções tratadas: SessaoExpirada (relogin automático), LoginFalhou;",
        "Pausa de 0,3s entre escolas.",
    ])

    # ------------------------------------------------------------------
    _par(story, estilos["h2"], "6.2 Dados dos Gestores Escolares")
    _par(story, estilos["corpo"],
         "Coleta o vínculo do gestor escolar e, quando disponível, as abas Identificação e Dados "
         "pessoais do formulário do gestor, gerando um XLSX com 3 abas (espelho de "
         "docs/modelo_coleta_gestor.xlsx).")
    _par(story, estilos["h3"], "Saída: XLSX único (vinculo_gestor_educacenso_DD-MM-AAAA.xlsx)")
    _tabela(story, estilos,
            ["Aba", "Colunas principais"],
            [
                ["Vínculo do gestor", "Código do Inep, Unidade Escolar, 1 - Cargo, 2 - Critério de acesso, 3 - Situação Funcional, Email principal."],
                ["Identificação", "Identificação única, CPF, Nome, data de nascimento, filiação 1/2, Sexo, Cor/Raça, Nacionalidade e outras (14)."],
                ["Dados pessoais", "País, CEP, UF, Município, Localização/zona, escolaridade, pós-graduações e outras (32)."],
            ],
            col_widths=[4.2, 12.8])
    _par(story, estilos["h3"], "Detalhes técnicos")
    _bullets(story, estilos["item"], [
        "Fluxo em fases por escola: seleção da escola, leitura do vínculo (filtro \"Apenas na escola\") e "
        "abertura do cadastro do gestor (abas Identificação/Dados pessoais);",
        "Nunca salva o formulário: fecha sempre com \"Cancelar\"/\"Fechar\";",
        "Detecta escola fechada e relogin automático em caso de sessão expirada;",
        "Arquivos temporários em /tmp/educacenso_gestor_tmp.",
    ])

    # ------------------------------------------------------------------
    _par(story, estilos["h2"], "6.3 Relatórios de Turmas, Alunos e Profissionais")
    _par(story, estilos["corpo"],
         "Três aplicações com a mesma tela (parametrizada): baixam o relatório CSV nativo do "
         "Educacenso para cada escola (relação turma-escola, aluno-escola ou profissional-escola) e "
         "empacotam tudo em um ZIP.")
    _par(story, estilos["h3"], "Saída: ZIP de CSVs")
    _tabela(story, estilos,
            ["Menu", "Prefixo do ZIP", "Conteúdo por escola"],
            [
                ["Relatórios de Turmas", "relatorio_turmas_educacenso", "relação turma-escola (CSV)"],
                ["Relatórios de Alunos", "relatorio_alunos_educacenso", "relação aluno-escola (CSV)"],
                ["Relatórios de Profissionais Escolares", "relatorio_profissionais_educacenso", "relação profissional-escola (CSV)"],
            ],
            col_widths=[5.4, 5.6, 6.0])
    _par(story, estilos["corpo"],
         "Dentro do ZIP, cada escola gera um CSV nomeado <b>{código_inep}_{nome da unidade}.csv</b> "
         "(nomes sanitizados; códigos repetidos recebem sufixos _2, _3, ...). O separador é ponto e "
         "vírgula (;) com codificação UTF-8 com BOM. Quando há escolas sem relatório, um XLSX "
         "adicional (escolas_nao_coletadas) lista código, nome e motivo.")
    _par(story, estilos["h3"], "Detalhes técnicos")
    _bullets(story, estilos["item"], [
        "Navegação por escola e geração do relatório (Gerar relatório, Gerar Excel, menu CSV);",
        "Download capturado via expect_download no contexto do navegador;",
        "Exceções: PreenchimentoNaoIniciado, RelatorioInexistente, SessaoExpirada, LoginFalhou;",
        "Arquivos temporários em /tmp/educacenso_relatorios_tmp.",
    ])

    # ------------------------------------------------------------------
    _par(story, estilos["h2"], "6.4 Recibos de Fechamento (1ª Etapa)")
    _par(story, estilos["corpo"],
         "Baixa o recibo de fechamento (PDF) de cada escola, disponível na tela /fechamento do "
         "Educacenso (link \"Recibo\" / \"Clique aqui para visualizar, salvar ou imprimir o recibo\"), "
         "e empacota em um ZIP.")
    _par(story, estilos["h3"], "Saída: ZIP de PDFs (recibos_fechamento_DD-MM-AAAA.zip)")
    _bullets(story, estilos["item"], [
        "Um PDF por escola, nomeado {código_inep}_{nome da unidade}.pdf (nomes sanitizados);",
        "XLSX de falhas (recibos_fechamento_escolas_nao_coletadas) com código, nome e motivo.",
    ])
    _par(story, estilos["h3"], "Detalhes técnicos")
    _bullets(story, estilos["item"], [
        "Procura o link do recibo em até 15 tentativas (intervalo de 1s);",
        "Valida os bytes do download (assinatura %PDF); conteúdo inválido é tratado como indisponível;",
        "Exceções: ReciboIndisponivel, LoginFalhou, SessaoExpirada;",
        "Arquivos temporários em /tmp/educacenso_recibos_fechamento_tmp.",
    ])

    # ==================================================================
    # 7. VERIFICAÇÃO DE INCONSISTÊNCIAS
    # ==================================================================
    _par(story, estilos["h1"], "7. Verificação de Inconsistências")
    _par(story, estilos["corpo"],
         "As cinco aplicações deste grupo validam os dados declarados no Educacenso e geram um "
         "relatório XLSX com as inconsistências encontradas. O fluxo comum é: carregar o arquivo de "
         "dados, validar as colunas, baixar as tabelas auxiliares quando disponíveis e iniciar a "
         "verificação; o relatório fica disponível para download na etapa final.")
    _par(story, estilos["corpo"],
         "Para as aplicações de Unidades e Gestor, a entrada é um XLSX exportado do Educacenso. Para "
         "as aplicações de Turmas, Aluno e Profissionais, a entrada é um ZIP com os CSVs exportados "
         "(um por escola, separador ; e UTF-8 com BOM).")

    # ------------------------------------------------------------------
    _par(story, estilos["h2"], "7.1 Cadastro de Unidades")
    _par(story, estilos["corpo"],
         "Valida as abas do cadastro da escola contra regras específicas. As mensagens indicam a "
         "coluna, o valor esperado e o valor encontrado.")
    _par(story, estilos["h3"], "Aba: Vinculação institucional e Conv")
    _tabela(story, estilos,
            ["Regra", "Condição esperada"],
            [
                ["2 - Regulamentação/autorização no conselho ou órgão", "Ser \"Sim\"."],
                ["Estadual", "Estar vazia."],
                ["Municipal", "Ser \"Sim\"."],
                ["3 - localizacaoZona", "Não pode estar vazia."],
                ["5 - A escola possui parceria ou convênio", "Ser \"Não\"."],
            ],
            col_widths=[8.5, 8.5])
    _par(story, estilos["h3"], "Aba: Funcionamento e Identificação")
    _tabela(story, estilos,
            ["Regra", "Condição esperada"],
            [
                ["6 - Situação de funcionamento", "Não pode estar vazia."],
                ["7a - Início", "Igual à data de início do ano letivo informada."],
                ["7b - Término (previsão)", "Igual à data de término informada."],
                ["9 - CEP", "Não pode estar vazio."],
                ["11b - Distrito", "Não pode estar vazio."],
                ["19 - Endereço eletrônico (e-mail)", "Não pode estar vazio."],
                ["20 - Localização diferenciada da escola", "Não pode estar vazio."],
            ],
            col_widths=[8.5, 8.5])
    _par(story, estilos["h3"], "Aba: Estrutura física")
    _tabela(story, estilos,
            ["Regra", "Condição esperada"],
            [
                ["Prédio escolar", "Ser \"Sim\"."],
                ["28 - Forma de ocupação do prédio escolar", "Não pode estar vazio."],
                ["29 - A escola compartilha o prédio com outra instituição", "Não pode estar vazio."],
                ["30 - Fornece água potável", "Não pode estar vazio."],
                ["Dormitório de professor(a)", "Deve estar vazio."],
                ["Laboratório específico para a educação profissional", "Deve estar vazio."],
                ["Sala de oficinas da educação profissional", "Deve estar vazio."],
            ],
            col_widths=[9.5, 7.5])
    _par(story, estilos["h3"], "Aba: Equipamentos e recursos tecnoló")
    _tabela(story, estilos,
            ["Regra", "Condição esperada"],
            [
                ["Computadores", "Ser \"Sim\"."],
                ["Não possui acesso à internet", "Deve estar vazio."],
                ["Para uso administrativo", "Ser \"Sim\"."],
                ["47 - Internet banda larga", "Ser \"Sim\"."],
            ],
            col_widths=[8.5, 8.5])
    _par(story, estilos["h3"], "Aba: Organização escolar")
    _tabela(story, estilos,
            ["Regra", "Condição esperada"],
            [
                ["49 - A escola fornece alimentação escolar", "Ser \"Oferece\"."],
                ["50 - Escola indígena", "Ser \"Não\"."],
                ["58 - A escola faz exame de seleção para ingresso", "Ser \"Não\"."],
            ],
            col_widths=[9.5, 7.5])

    # ------------------------------------------------------------------
    _par(story, estilos["h2"], "7.2 Cadastro de Gestor")
    _par(story, estilos["corpo"],
         "Valida as três abas do cadastro do gestor. As mensagens indicam a coluna e o valor esperado.")
    _par(story, estilos["h3"], "Aba: Vínculo do gestor")
    _tabela(story, estilos,
            ["Regra", "Condição esperada"],
            [
                ["1 - Cargo", "Ser \"Diretor(a)\"."],
                ["2 - Critério de acesso ao cargo/função", "Não vazio e fora dos valores proibidos (processo eleitoral / concurso público específico)."],
                ["3 - Situação Funcional/Regime de contratação/Tipo de vínculo", "Ser \"Concursado/efetivo/estável\" ou \"Contrato temporário\"."],
                ["Email principal", "Não pode estar vazio."],
            ],
            col_widths=[6.5, 10.5])
    _par(story, estilos["h3"], "Aba: Identificação")
    _tabela(story, estilos,
            ["Regra", "Condição esperada"],
            [
                ["5a - Nome completo da filiação 1", "Não pode estar vazio."],
                ["5b - Nome completo da filiação 2", "Não pode estar vazio."],
                ["6 - Sexo", "Não pode estar vazio."],
                ["7 - Cor/Raça", "Não pode ser \"Não declarada\"."],
                ["8 - Nacionalidade", "Não pode estar vazio."],
                ["10 - UF de nascimento", "Não pode estar vazio."],
                ["11 - Município de nascimento", "Não pode estar vazio."],
            ],
            col_widths=[7.0, 10.0])
    _par(story, estilos["h3"], "Aba: Dados pessoais")
    _tabela(story, estilos,
            ["Regra", "Condição esperada"],
            [
                ["13 - País de residência", "Não pode estar vazio."],
                ["14 - CEP", "Não pode estar vazio."],
                ["15 - UF", "Não pode estar vazio."],
                ["16 - Município", "Não pode estar vazio."],
                ["17 - Localização/zona de residência", "Não pode estar vazio."],
                ["18 - Localização diferenciada da residência", "Não pode estar vazio."],
                ["19 - Maior nível de escolaridade concluído", "Ser \"Educação superior\"."],
                ["19a - Tipo de ensino médio cursado", "Não pode estar vazio."],
                ["20. Pós-graduações concluídas", "Não pode estar vazio."],
            ],
            col_widths=[7.0, 10.0])

    # ------------------------------------------------------------------
    _par(story, estilos["h2"], "7.3 Cadastro de Turmas")
    _par(story, estilos["corpo"],
         "A entrada é um ZIP com os CSVs de turmas (um por escola). O sistema separa as tabelas "
         "turmas_aee, turmas_atvcomplementar, turmas_curricular e turmas_escolarizacao. Na tabela de "
         "escolarização são criadas duas colunas derivadas a partir do campo Nome da turma:")
    _bullets(story, estilos["item"], [
        "<b>periodo_turma</b>: os 2 primeiros caracteres do Nome da turma;",
        "<b>verifica_integral</b>: o 3º caractere do Nome da turma.",
    ])
    _par(story, estilos["corpo"],
         "As regras abaixo são aplicadas exclusivamente na tabela de escolarização. As regras da "
         "tabela curricular são aplicadas separadamente. As mensagens exatas são indicadas em cada regra.")

    _par(story, estilos["h3"], "7.3.1 Sigla para Etapa de ensino (mensagem: Divergência entre Sigla e Etapa)")
    _tabela(story, estilos,
            ["periodo_turma", "Etapa de ensino esperada"],
            [
                ["1A", "Ensino fundamental de 9 anos - 1º Ano"],
                ["2A", "Ensino fundamental de 9 anos - 2º Ano"],
                ["3A", "Ensino fundamental de 9 anos - 3º Ano"],
                ["4A", "Ensino fundamental de 9 anos - 4º Ano"],
                ["5A", "Ensino fundamental de 9 anos - 5º Ano"],
                ["6A", "Ensino fundamental de 9 anos - 6º Ano"],
                ["7A", "Ensino fundamental de 9 anos - 7º Ano"],
                ["8A", "Ensino fundamental de 9 anos - 8º Ano"],
                ["9A", "Ensino fundamental de 9 anos - 9º Ano"],
                ["1F, 2F, 3F, 4F, 5F", "EJA - Ensino fundamental - anos iniciais (1º segmento)"],
                ["6F, 7F, 8F, 9F", "EJA - Ensino fundamental - anos finais (2º segmento)"],
                ["G1, G2, G3", "Educação infantil - creche (0 a 3 anos)"],
                ["P1, P2", "Educação infantil - pré-escola (4 e 5 anos)"],
                ["MF", "EJA - Ensino fundamental - anos iniciais (1º segmento) OU anos finais (2º segmento)"],
                ["NI, NF", "Ensino Fundamental de 9 anos - correção de fluxo"],
                ["MA", "Ensino Fundamental de 9 anos - multi"],
            ],
            col_widths=[4.0, 13.0])

    _par(story, estilos["h3"], "7.3.2 Prefixo MI (mensagem: Divergência entre Sigla e Etapa)")
    _par(story, estilos["corpo"],
         "Para turmas com periodo_turma igual a <b>MI</b>, a coluna Etapa Agregada deve ser igual a "
         "Educação Infantil; caso contrário, é registrada a inconsistência.")

    _par(story, estilos["h3"], "7.3.3 Etapa de ensino para Sigla (mensagem: Divergência entre Sigla e Etapa)")
    _tabela(story, estilos,
            ["Etapa de ensino", "periodo_turma esperado"],
            [
                ["Ensino Fundamental de 9 anos - multi", "MA"],
                ["Ensino Fundamental de 9 anos - correção de fluxo", "NI ou NF"],
                ["Educação infantil e ensino fundamental - multietapa", "IF"],
            ],
            col_widths=[12.0, 5.0])

    _par(story, estilos["h3"], "7.3.4 Carga horária semanal (hh:mm)")
    _tabela(story, estilos,
            ["verifica_integral", "Regra", "Mensagem"],
            [
                ["M ou T", "Carga horária semanal não pode ser menor que 20:00:00 nem maior que 35:00:00.",
                 "Carga Horária menor que 20h ou maior do que 35h."],
                ["I", "Carga horária semanal deve ser maior ou igual a 35:00:00.",
                 "Integral não pode ser inferior a 35h"],
            ],
            col_widths=[3.2, 8.3, 5.5])

    _par(story, estilos["h3"], "7.3.5 Regras da tabela curricular")
    _tabela(story, estilos,
            ["Regra", "Condição esperada"],
            [
                ["Tipo de turma", "Ser \"Curricular (etapa de ensino)\"."],
                ["Nome da turma", "Informado, com exatamente 5 caracteres e sem espaços."],
                ["3º caractere do Nome da turma", "Ser M, T, N ou I."],
                ["Formas de organização (quando EJA)", "Ser \"Períodos semestrais\"."],
                ["Carga horária - EJA anos iniciais", "Entre 15:00:00 e 20:00:00."],
                ["Carga horária - Ensino Fundamental / Educação Infantil", "Não menor que 20:00:00."],
                ["Carga horária - 3º caractere I", "Maior ou igual a 35:00:00."],
                ["Dias da semana e horário de funcionamento", "Não conter Sábado ou Domingo."],
                ["Áreas do conhecimento/componentes curriculares", "Conforme a etapa de ensino (sem áreas faltantes ou extras)."],
                ["Turma de Educação Especial / Bilingue de Surdos / Formação por Alternância", "Ser \"Não\"."],
            ],
            col_widths=[7.5, 9.5])

    # ------------------------------------------------------------------
    _par(story, estilos["h2"], "7.4 Cadastro de Aluno")
    _par(story, estilos["corpo"],
         "A entrada é um ZIP com os CSVs de alunos. A validação usa a tabela aluno_curricular e roda "
         "automaticamente após o processamento do ZIP (sem botão de validação). A idade é calculada "
         "completa em 31/03 do ano letivo selecionado, a partir da Data de nascimento.")
    _par(story, estilos["h3"], "Regras de validação")
    _tabela(story, estilos,
            ["Regra", "Mensagem exata"],
            [
                ["Localização/Zona de residência vazia", "Sem Zona Residencial informada"],
                ["Transporte escolar = Sim e Poder Público responsável diferente de Municipal",
                 "Transporte Escolar não informado como Municipal"],
                ["Idade incompatível com o período (G1=0/1, G2=2, G3=3, P1=4, P2=5, MI=até 5)",
                 "Idade incompatível com turma"],
                ["Idade incompatível com a etapa (creche até 3, pré-escola 4/5, EJA a partir de 15, EF 9 anos a partir de 6)",
                 "Idade incompatível com turma"],
            ],
            col_widths=[11.0, 6.0])
    _par(story, estilos["h3"], "Relatórios de apoio (tela de Aluno)")
    _tabela(story, estilos,
            ["Relatório", "Critério"],
            [
                ["Matrículas em Duplicidade (XLSX)", "Mesmo CPF e/ou mesma Identificação única em mais de um registro."],
                ["Matrículas sem CPF informado (XLSX)", "Coluna CPF vazia, com \"--\" ou NaN."],
                ["Quantitativo de Cor/Raça por Unidade Escolar", "Contagem por escola dos valores de Cor/Raça (preta, parda, branca, amarela, indígena, não declarado, sem informação)."],
            ],
            col_widths=[8.0, 9.0])

    # ------------------------------------------------------------------
    _par(story, estilos["h2"], "7.5 Cadastro de Profissionais Escolares")
    _par(story, estilos["corpo"],
         "A entrada é um ZIP com os CSVs de profissionais. A validação agrupa as inconsistências por "
         "profissional (Código do Inep + Identificação única) e deduplica as regras.")
    _tabela(story, estilos,
            ["Regra", "Mensagem exata"],
            [
                ["Situação funcional como Contrato CLT ou terceirizado",
                 "Situação Funcional informada como 'Contrato CLT ou Terceirizado informado'"],
                ["Itinerário formativo informado (IFA)",
                 "Itinerário formativo não deve ser informado"],
                ["Tipo do curso do itinerário informado",
                 "Itinerário formativo não deve ser informado"],
                ["Cor/Raça \"Não declarada\"",
                 "Etnia informada como Não Declarado"],
                ["Localização/Zona de residência vazia",
                 "Zona da residência não informada"],
                ["Localização diferenciada de residência vazia",
                 "Localização diferenciada não informada"],
                ["Escolaridade como Ensino fundamental",
                 "Escolarização do Profissional informada como Ensino fundamental"],
                ["Professor de anos finais (6º a 9º ano) sem Educação superior",
                 "Professor de Anos Finais Sem Ensino Superior"],
            ],
            col_widths=[10.5, 6.5])

    # ==================================================================
    # 8. PADRÕES TÉCNICOS E ARQUITETURA
    # ==================================================================
    _par(story, estilos["h1"], "8. Padrões Técnicos e Arquitetura")
    _par(story, estilos["corpo"],
         "Todas as aplicações seguem o mesmo esqueleto: auth.py (autenticação), scraper, frontend.py, "
         "upload.py, exporter ou zipper e modelo.py. Os templates de modelo ficam em "
         "docs/modelo_coleta.xlsx (6 abas) e docs/modelo_coleta_gestor.xlsx.")
    _par(story, estilos["h2"], "8.1 Automação e autenticação")
    _bullets(story, estilos["item"], [
        "Sempre Playwright sync_api (nunca async);",
        "READ_ONLY = True em todos os auth.py - jamais escrever dados no Educacenso;",
        "Fluxo de login via Keycloak em acesso.inep.gov.br (CPF + senha);",
        "Hierarquia de exceções: SessaoExpirada, LoginFalhou, ReciboIndisponivel, "
        "PreenchimentoNaoIniciado, RelatorioInexistente;",
        "Logs personalizados em português (logger = logging.getLogger(\"coleta_*\")).",
    ])
    _par(story, estilos["h2"], "8.2 Reuso de sessão e temporários")
    _bullets(story, estilos["item"], [
        "run_scraping() mantém um contexto de navegador e refaz o login se a sessão expirar;",
        "Arquivos temporários: /tmp/educacenso_tmp, /tmp/educacenso_gestor_tmp, "
        "/tmp/educacenso_relatorios_tmp e /tmp/educacenso_recibos_fechamento_tmp;",
        "Consolidação final no fim da coleta (exporter.py para XLSX via openpyxl, zipper.py para ZIP).",
    ])
    _par(story, estilos["h2"], "8.3 Entrada e saída de dados")
    _bullets(story, estilos["item"], [
        "Entrada: XLSX com as colunas código do inep e nome da unidade (tolerante a maiúsculas via upload.py);",
        "Saída de escolas: XLSX único com 6 abas (CSV para openpyxl);",
        "Saída de relatórios: ZIP de CSVs via zipper.py;",
        "Saída de recibos: ZIP de PDFs via zipper.py;",
        "Saída Google Sheets (sheets.py): escreve na planilha do usuário quando credenciais são fornecidas.",
    ])

    # ==================================================================
    # 9. TESTES
    # ==================================================================
    _par(story, estilos["h1"], "9. Testes")
    _bullets(story, estilos["item"], [
        "Apenas tests/security/ existe no projeto;",
        "33 testes de segurança, pulados por padrão (exigem SECURITY_LIVE=1);",
        "Alvo padrão: https://censoescolar.streamlit.app/ (sobrescrevível com SECURITY_TARGET);",
        "Não intrusivos: poucas requisições, sem fuzzing nem brute-force;",
        "Níveis: \"app\" versus \"plataforma\" nos achados;",
        "Comando de auditoria ao vivo: SECURITY_LIVE=1 uv run python -m pytest tests/security/.",
    ])

    # ==================================================================
    # 10. LICENÇA E CONTATO
    # ==================================================================
    _par(story, estilos["h1"], "10. Licença e Contato")
    _bullets(story, estilos["item"], [
        "Código aberto sob GNU Affero General Public License v3.0 (AGPL-3.0);",
        "Licença alternativa para uso governamental ou comercial (Prefeituras, Secretarias, órgãos "
        "públicos e empresas) com suporte técnico dedicado;",
        "Contato: rodrigo.nunes@edu.campos.rj.gov.br;",
        "Isenção de responsabilidade e LGPD: o software roda localmente, não coleta, armazena nem "
        "acessa dados de alunos ou escolas; a entidade operadora é a única Controladora dos dados.",
    ])

    # ==================================================================
    # APÊNDICE
    # ==================================================================
    _par(story, estilos["h1"], "Apêndice A - Modelos de Entrada")
    _tabela(story, estilos,
            ["Modelo", "Localização", "Conteúdo"],
            [
                ["modelo_coleta.xlsx", "docs/modelo_coleta.xlsx", "6 abas: Vinculação institucional e Conv, Funcionamento e Identificação, Estrutura física, Equipamentos e recursos tecnológicos, Recursos humanos e Organização escolar."],
                ["modelo_coleta_gestor.xlsx", "docs/modelo_coleta_gestor.xlsx", "Aba Vínculo do gestor (1 aba no modelo)."],
            ],
            col_widths=[4.6, 4.6, 7.8])
    _par(story, estilos["corpo"],
         "Observação: arquivos de dados (.xlsx, .xls, .csv, .log) são ignorados pelo Git e não devem "
         "ser versionados.")

    doc.multi_build(story)
    buf.seek(0)
    return buf.getvalue()
