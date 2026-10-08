# Guia do Agent — Aplicações de Apoio Censo Escolar

## Comandos principais

```bash
uv run streamlit run app.py                        # inicia o HUB
uv run python -m pytest                             # testes de segurança (pulados sem SECURITY_LIVE=1)
SECURITY_LIVE=1 uv run python -m pytest tests/security/  # auditoria ao vivo
uv add <pacote>                                     # adicionar dependência
```

## Arquitetura

- **Entrypoint**: `app.py` — HUB Streamlit com navegação lateral
- **5 apps** em `apps/`, cada uma autocontida com `src/`:
  - `inicio/` — apenas página inicial
  - `coleta_cadastros_escolas/` — raspa dados de escolas do Educacenso → XLSX
  - `coleta_gestor/` — raspa dados de gestores → XLSX
  - `coleta_relatorios/` — baixa relatórios CSV (turmas/alunos/profissionais) → ZIP
  - `coleta_recibos_fechamento/` — baixa recibos PDF → ZIP
- **Todas seguem o mesmo padrão**: `auth.py` + scraper + `frontend.py` + `upload.py` + exporter/zipper + `modelo.py`
- **Templates de modelo**: `docs/modelo_coleta.xlsx` (6 abas) e `docs/modelo_coleta_gestor.xlsx` (1 aba)

## Convenções de scraping

- **Sempre usar `playwright.sync_api`** (nunca async)
- **`READ_ONLY = True`** em todo `auth.py` — jamais escrever dados no Educacenso
- **Fluxo de login**: Keycloak em `acesso.inep.gov.br`, CPF + senha
- **Hierarquia de exceções**: `SessaoExpirada`, `LoginFalhou`, `ReciboIndisponivel`, `PreenchimentoNaoIniciado`
- **Logs personalizados em português** (`logger = logging.getLogger("coleta_*")`)
- **Reuso de sessão com retry**: `run_scraping()` mantém um browser context, refaz login se expirar
- **Arquivos temporários**: apps escrevem CSVs em `/tmp/educacenso_tmp` ou `/tmp/educacenso_relatorios_tmp` durante coleta, depois consolidam no final

## Entrada/Saída de dados

- **Entrada**: XLSX com colunas `código do inep` + `nome da unidade` (tolera maiúsculas/minúsculas via `upload.py`)
- **Saída de dados de escolas**: XLSX único com 6 abas, construído via `exporter.py` (CSV → openpyxl)
- **Saída de relatórios**: ZIP de CSVs via `zipper.py`
- **Saída de recibos**: ZIP de PDFs via `zipper.py`
- **Saída Google Sheets** (`sheets.py`): escreve na planilha do usuário quando credenciais são fornecidas

## Ambiente e secrets

- **Credenciais**: `apps/coleta_cadastros_escolas/docs/credenciais.json` (gitignored)
- **`.streamlit/secrets.toml`** (gitignored)
- **Dependências de sistema para Playwright** em `packages.txt` (libnss3, libnspr4, etc.)
- Chromium instalado automaticamente na primeira execução via `playwright install chromium` (ver `_ensure_chromium()`)

## Testes

- Apenas `tests/security/` existe
- **Pulados por padrão** — exigem `SECURITY_LIVE=1`
- Alvo: `https://censoescolar.streamlit.app/` (sobrescreve com `SECURITY_TARGET`)
- Não intrusivos: poucas requisições, sem fuzzing/brute-force
- Níveis: "app" vs "plataforma" nos achados

## .gitignore — Atenção

- `.xlsx`, `.xls`, `.csv`, `.log` são **todos gitignorados** — não espere commitar arquivos de dados
- `.opencode/` é gitignorado

## Arquivos de agente existentes

- `.opencode/agents/engenheiro-de-dados.md` — diretrizes de scraping/ETL
- `.opencode/agents/analista-de-dados.md` — diretrizes de relatórios/análise (bash somente leitura)
- Respeite esses arquivos para tarefas especializadas dos subagentes

## Estado atual — app de Verificação de Inconsistências (2026-08-04)

Implementado e verificado (compilação + teste funcional OK; 33 testes de segurança pulados por padrão):

1. **Listagem "Matrículas sem CPF informado (XLSX)"** (tela Cadastro de Aluno):
   - `rules/aluno.py` → `extrair_alunos_sem_cpf(df)`: retorna registros cuja coluna `CPF` é `'--'`, vazia ou `NaN` (via `_normalizar`). Campos: `codigo_inep`, `nome_unidade`, `identificacao_unica`, `nome`, `cpf`. Ordena por INEP + nome.
   - Exportado em `rules/__init__.py` e registrado em `validations.py` como `VALIDATIONS["aluno"]["extrair_sem_cpf"]`.
   - `frontend.py` → `_sem_cpf_xlsx(registros)` gera XLSX com colunas: Código do Inep, Unidade Escolar, Identificação Única, Nome do Aluno, CPF.
   - Botão renderizado em `frontend.py` (bloco "RELATÓRIOS DE APOIO", depois de "Matrículas em Duplicidade" e antes de "Quantitativo de Cor/Raça"). Se não houver registros, mostra warning.

2. **Seletor "Ano letivo"** (somente na tela Cadastro de Aluno — `is_aluno`):
   - `st.selectbox` de anos (decrescente, 2026→2000) no formulário; valor salvo em `st.session_state[{prefix}ano_letivo]`; default no `_init_state` = ano atual.
   - CSS aplicado apenas em `is_aluno`: dropdown do listbox com `width: 5cm` e `max-height: 360px` (visor +20%).

3. **Rótulos de botões** (sem prefixo "Baixar"): "Matrículas em Duplicidade (XLSX)", "Matrículas sem CPF informado (XLSX)", "Quantitativo de Cor/Raça por Unidade Escolar".

4. **Validação de Alunos** (`validate_aluno` em `rules/aluno.py`, usa a tabela `aluno_curricular`):
   - **Entrada**: `(df_aluno_curricular, escolas, ano_letivo)` — chamada automaticamente na tela Aluno (frontend passa o `ano_letivo` do `st.selectbox`).
   - **Regras simples**: `Localização/Zona de residência` vazio → `Sem Zona Residencial informada`; quando `Transporte escolar (Sim/Não)` == `Sim`, `Poder Público responsável` ≠ `Municipal` → `Transporte Escolar não informado como Municipal`.
   - **Regras de idade** (todas com texto `Idade incompatível com turma`): calcula `idade` completa em 31/03/{ano_letivo} a partir de `Data de nascimento`; `periodo` = 2 primeiros caracteres de `Nome da turma`. Períodos: G1=0/1, G2=2, G3=3, P1=4, P2=5, MI=≤5. Etapas: creche ≤3, pré-escola 4/5, EJA ≥15, EF 9 anos (correção de fluxo/multi/1º-9º) ≥6.
   - **Relatório** (`_build_xlsx` modo `"aluno"`, via `_modo_relatorio`): colunas Codigo do Inep, Unidade Escolar, Identificação Única, Nome do Aluno, Data de nascimento, Idade, Nome da Turma, Etapa de ensino + INCONSISTENCIA 1..N (sem coluna Período).
   - **Execução automática**: na tela Aluno a validação roda sozinha assim que o ZIP é processado e as colunas validadas (sem botão de validação). `validate_aluno` é chamado com `df_aluno_curricular` + `ano_letivo`, só quando `resultados` ainda é `None`.
   - Resultados exibidos na Etapa 3 (tela Aluno) com botão "Relatório de Inconsistências (XLSX)".
   - Constantes de coluna: `COL_LOCALIZACAO`, `COL_TRANSPORTE`, `COL_PODER_PUBLICO`, `COL_NASCIMENTO`, `COL_ETAPA_ENSINO` em `rules/aluno.py`. Resultado inclui `data_nascimento` e `idade`.

5. **Spinners de carregamento** (frontend.py): 
   - Listagem de download (`opcoes`, bloco LISTAGEM): `st.spinner("Carregando Listagem de Alunos/Turmas/Profissionais...")` conforme a tela.
   - "RELATÓRIOS DE APOIO" (tela Aluno): `st.spinner("Carregando Relatórios de Apoio...")`.
   - Validações (`config["validate"]` — aluno automático, botão das telas Turmas/Profissionais/ZIP/planilha) e `_build_xlsx` da Etapa 3: `st.spinner("Carregando Relatório de Inconsistências...")`.
   - Totalizador ("Total de Inconsistencias"/"Total de Unidades") exibido somente fora da tela Aluno (`if not is_aluno`).

6. **Validação de Turmas — regras da tabela Escolarização** (`rules/turmas.py`, mescladas ao relatório de turmas):
   - `upload.py` → `read_turmas_zip` adiciona as colunas derivadas `periodo_turma` (2 primeiros chars de `Nome da turma`) e `verifica_integral` (3º char) apenas em `turmas_escolarizacao` (o XLSX exportado "Turmas Escolarização" já sai com elas).
   - `validate_turmas_escolarizacao(df_escolarizacao)` roda **somente** na escolarização; `validate_turmas(..., df_escolarizacao=None)` mescla esses resultados com os da curricular. `frontend.py` passa `df_escol` na chamada da validação.
   - Regras (mensagens exatas): sigla→etapa (`1A-9A`→EF 9 anos, `1F-5F`→EJA inic, `6F-9F`→EJA fin2, `G1-G3`→creche, `P1/P2`→pré, `MF`→EJA inic**ou**fin2, `NI/NF`→correção, `MA`→multi) e etapa→sigla (multi→`MA`, correção→`NI`/`NF`, multietapa→`IF`) → `Divergência entre Sigla e Etapa` (deduplicada por linha); char3 `M`/`T` → carga fora de [20h,35h] → `Carga Horária menor que 20h ou maior do que 35h.`; char3 `I` → carga < 35h → `Integral não pode ser inferior a 35h`. Comparação de etapa por substring (`_contem`, tolera hífen/en-dash na "multietapa").
   - Relatório turmas (`_build_xlsx` modo `"turma"`) agora inclui colunas de contexto: Etapa de ensino, Carga horária semanal (hh:mm), periodo_turma, verifica_integral. Resultados carregam esses campos.

7. **Documentação completa em PDF** (tela inicial — `apps/inicio/`):
   - `documentacao.py` → `build_documentacao_pdf(logo_base64=None) -> bytes`: gera PDF A4 dinâmico com **reportlab==5.0.0** (pura Python, sem LaTeX). Capa (logo opcional), sumário via `TableOfContents` + `multiBuild`, rodapé paginado, tabelas com células `Paragraph`. Conteúdo: visão geral (10 apps), requisitos, instalação/execução, segurança/LGPD, coleta (cadastro escolas 6 abas, gestores 3 abas, relatórios ZIP CSVs, recibos ZIP PDFs), verificação (unidades 5 abas, gestor 3 abas, turmas incl. MI, aluno, profissionais 7 regras), arquitetura, testes, licença/contato, modelos de entrada.
   - `inicio.py` → `@st.cache_data _documentacao_pdf_bytes(logo_base64)` + `st.download_button` centralizado ("Baixar Documentação Completa (PDF)") com nome `Documentacao_Aplicacoes_Apoio_Censo_Escolar_{DD-MM-AAAA}.pdf`, `mime="application/pdf"`.
   - Detalhes reportlab 5: `TableOfContents` vem de `reportlab.platypus.tableofcontents` (não mais reexportado em `platypus`); `ParagraphStyle(parent=...)` exige instância de estilo (não nome string); margens/colunas/Image devem usar `reportlab.lib.units.cm`.

8. **Pendência aberta**: usuário relatou que "uma mensagem pisca e desaparece" ao alternar entre as apps de inconsistências. Análise: não há `st.toast`; provavelmente é o banner de status da página anterior durante o `st.rerun()` do `app.py:628`, ou a animação CSS `fadeIn 0.7s` do `.title-container` (app.py:325). Aguardando o usuário confirmar qual. A limpeza de estado em `app.py:642-650` já zera `session_state` na troca de página.
