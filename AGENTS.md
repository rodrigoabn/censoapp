# Guia do Agent — Aplicações de Apoio Censo Escolar

## Comandos principais

```bash
uv run streamlit run app.py --server.port 8501      # sobe o HUB (sem Docker; porta escolhida na hora)
uv sync                                              # cria/atualiza o .venv e as dependências
uv run playwright install --with-deps chromium       # uma vez no host (libs do Chromium)
uv run python -m pytest                             # suíte offline (segurança pulada sem SECURITY_LIVE=1)
uv run ruff check .                                 # lint (config no pyproject)
SECURITY_LIVE=1 SECURITY_TARGET=http://localhost:8501/ uv run python -m pytest tests/security/  # auditoria HTTP ao vivo
uv add <pacote>                                     # adicionar dependência
```

## Arquitetura

- **Entrypoint**: `app.py` — HUB Streamlit com navegação lateral
- **7 apps** em `apps/` + **4 coletores headless** (sem tela), com código compartilhado em `apps/common/` (`auth`, `banner`, `browser`, `coleta`, `export`, `orientacoes`, `school_list`, `session`, `ui`):
  - `inicio/` — página inicial + documentação completa em PDF
  - `coleta_automatica/` — tela única de coleta: roda as 6 etapas do Educacenso em sequência, em background, e gera um ZIP único com o tempo de cada etapa
  - `coleta_cadastros_escolas/` — coletor headless: raspa dados de escolas do Educacenso → XLSX (6 abas), em `src/collector.py`
  - `coleta_gestor/` — coletor headless: raspa dados de gestores → XLSX (3 abas), em `src/collector.py`
  - `coleta_relatorios/` — coletor headless: baixa relatórios CSV (turmas/alunos/profissionais) → ZIP, em `src/collector.py`
  - `coleta_recibos_fechamento/` — coletor headless: baixa recibos PDF → ZIP, em `src/collector.py`
  - `adequacao_turmas/` — converte o ZIP de turmas no layout padronizado → ZIP
  - `adequacao_alunos/` — converte o ZIP de alunos no layout padronizado → ZIP
  - `adequacao_profissionais/` — converte o ZIP de profissionais no layout padronizado → ZIP
  - `verificacao_inconsistencias/` — aponta inconsistências nos ZIPs/planilhas (regras em `src/rules/`) → XLSX
  - `unificador_inconsistencias/` — unifica os relatórios de inconsistências por unidade escolar → XLSX
- **As coletas seguem o mesmo padrão**: `auth.py` + scraper + `collector.py` (`CONFIG` + worker headless) + exporter/zipper + `modelo.py`; a lista de escolas vem de `apps/common/school_list.py`. Não há telas isoladas de coleta: a única tela é a da Coleta de Dados.
- **Relógio da coleta**: a tela da rodada lê o horário inicial/término de `apps/common/ui.py` e desenha o relógio digital (`RELOGIO_CSS`, `_relogio_*_conteudo_html`) a cada 0,5s via `st.fragment`; ao final, o resumo dos tempos aparece junto do download.
- **Coleta de Dados** (`apps/coleta_automatica/`): roda as 6 coletas em sequência numa thread (`src/runner.py`), reaproveitando o worker de cada coletor headless (`src/etapas.py` importa `collector.py`); a tela (`src/frontend.py`) mostra o relógio, o tempo por etapa e o download de cada artefato, e entrega o ZIP único. Etapa sem coleta → a rodada **pausa e pergunta**; etapa com erro → a rodada **para**.
- **Layout comum das telas**: cabeçalho padrão (logo + título + subtítulo, sobre o cartão `.title-container`) renderizado por `apps/common/banner.py` (`banner_titulo`) + conteúdo principal em `st.columns([1.4, 1])`; o card "Orientações de uso" fica sempre na coluna direita e é renderizado por `apps/common/orientacoes.py` (`card_orientacoes`). **Nenhuma tela pode pôr o card de Orientações em largura total** — o texto encosta à esquerda e deixa metade da linha vazia (foi o caso da Coleta de Dados, corrigido em `apps/coleta_automatica/src/frontend.py`: `_tela_formulario` abre `st.columns(COLS_ORIENTACOES)` e desenha o `card_orientacoes` em `col_help`; o upload da lista de escolas fica em largura integral para o aviso de tamanho não ser cortado)
- **Botões**: o botão de ação de toda tela chama-se **Executar** (inclusive nas 3 apps de adequação, nas 5 telas de verificação e no unificador) e todos os botões da área de conteúdo (`stButton`, `stDownloadButton` e submit de formulário) são azuis (`--status-info`); o menu lateral mantém o estilo de item de menu (transparente, item ativo em azul)
- **Templates de modelo**: `apps/coleta_cadastros_escolas/docs/modelo_coleta.xlsx` (6 abas) e `apps/coleta_gestor/docs/modelo_coleta_gestor.xlsx` (3 abas); referências de estrutura (só cabeçalho) em `apps/verificacao_inconsistencias/docs/`

## Convenções de scraping

- **Sempre usar `playwright.sync_api`** (nunca async)
- **`READ_ONLY = True`** em todo `auth.py` — jamais escrever dados no Educacenso
- **Fluxo de login**: Keycloak em `acesso.inep.gov.br`, CPF + senha
- **Hierarquia de exceções**: `SessaoExpirada`, `LoginFalhou`, `ReciboIndisponivel`, `PreenchimentoNaoIniciado`
- **Senha incorreta**: `login_and_read` captura a mensagem exibida pelo
  Keycloak (`.kc-feedback-text`, `#input-error`, `.alert-error`) e levanta
  `LoginFalhou(mensagem)`; `run_coleta` loga o motivo e **aborta a etapa** (não
  devolve as escolas como "Falha no login"). A rodada marca a etapa como
  `falhou`, não pausa e a tela orienta "Login ou senha incorretos" (sem botão
  Continuar). O login só é repetido quando o portal não exibiu mensagem
  (instabilidade).
- **Logs personalizados em português** (`logger = logging.getLogger("coleta_*")`)
- **Nova tentativa em timeout (só na rodada)**: escola que falha por timeout do
  Playwright (`wait_for_selector`, `goto`, `click`, `expect_download`) é repetida
  **na hora**, até **5 tentativas no total** (1 original + 4 repetições), com
  **5 s** entre elas; a fila **não avança** enquanto as tentativas da escola atual
  não terminarem (a espera é interrompível: a parada do usuário vence). Só a
  tentativa bem-sucedida grava — `scrape_one`/`registrar_sucesso` escrevem uma
  única vez, então nada da tentativa que errou sobra no artefato. O retry mora no
  laço compartilhado (`coleta.com_tentativas_timeout`) e é ligado pela rodada via
  `ContextVar` (`TENTATIVAS_TIMEOUT` = 5, `ESPERA_TENTATIVAS` = 5.0; default 1
  fora da rodada, em chamadas diretas e testes); a falha carrega
  `"timeout": bool`. Na rodada a navegação interna usa **1** tentativa
  (`session.TENTATIVAS_NAVEGACAO`); o default fora da rodada continua **3**.
- **Reuso de sessão com retry**: `run_scraping()` mantém um browser context, refaz login se expirar
- **Arquivos temporários**: cada execução cria uma pasta exclusiva (`nova_pasta_temporaria()`, prefixos `educacenso_*_tmp_`) em `/tmp` para os CSVs/PDFs da coleta; a consolidação (`build_xlsx`/`build_zip`) remove a pasta no final

## Entrada/Saída de dados

- **Entrada**: XLSX com colunas `código do inep` + `nome da unidade` (tolera maiúsculas/minúsculas via `apps/common/school_list.py`)
- **Saída de dados de escolas**: XLSX único com 6 abas, construído via `exporter.py` (CSV → openpyxl)
- **Saída de relatórios**: ZIP de CSVs via `zipper.py`
- **Saída de recibos**: ZIP de PDFs via `zipper.py`

## Credenciais e ambiente

- **Credenciais**: `apps/coleta_cadastros_escolas/docs/credenciais.json` (gitignored; atualmente removido — recrie localmente quando for coletar e nunca versione).
- **Sem autenticação própria e sem `.streamlit/secrets.toml`**: o HUB roda na rede local, em HTTP puro; o acesso é controlado pela rede (firewall/VPN) e as credenciais do Educacenso protegem as coletas. Credenciais, uploads e relatórios com PII não são criptografados em trânsito — veja `docs/deploy.md`.
- **Dependências de sistema para Playwright** em `packages.txt` (libnss3, libnspr4, etc.) — instale com `uv run playwright install --with-deps chromium` ou pelo gerenciador de pacotes da distribuição
- Chromium é baixado automaticamente na primeira coleta (`ensure_chromium()`); no host, as libs de sistema precisam existir antes

## Execução local — uv (sem Docker na operação)

- **Runbook completo**: `docs/deploy.md` (pré-requisitos, `uv sync`, Chromium, porta, logs, testes e troubleshooting).
- **Subir**: `uv run streamlit run app.py --server.port <porta>` na raiz do projeto; a porta é escolhida a cada execução (padrão 8501). O HUB escuta em `0.0.0.0`; restrinja a porta à rede local/VPN.
- **Sem autenticação de aplicação**: não há `auth_gate.py`, Caddy ou compose; a aplicação é servida em HTTP puro por padrão. O reinício após queda fica a cargo do script externo do operador (journal), que deve chamar o comando `uv`.
- **Logging** (`logging_setup.py`, idempotente a cada rerun): arquivo rotativo `censoapp.log` (5 MB × 5) em `CENSO_LOG_DIR` (padrão `./logs`); se não for gravável, cai para o stderr e o HUB segue no ar; nunca registrar PII.
- **CI**: `.github/workflows/ci.yml` (push/PR → `uv sync --frozen` + `ruff check .` + `pytest -q`).

## Testes

- `tests/` cobre a suíte offline (fakes, sem rede): `uv run python -m pytest` → 720 passed / 18 skipped; lint com `uv run ruff check .`
- `tests/security/` é ao vivo; **os 18 testes HTTP de segurança são pulados por padrão** — exigem `SECURITY_LIVE=1`
- Alvo via `SECURITY_TARGET` (**obrigatório** — sem padrão; ex.: `http://localhost:8501/`); não há TLS/HSTS/Caddy nesta modalidade
- Não intrusivos: poucas requisições, sem fuzzing/brute-force
- Escopo: métodos HTTP e exposição de caminhos/arquivos sensíveis

## .gitignore — Atenção

- `*.xlsx`, `*.xls`, `*.csv`, `*.log` são **gitignorados por padrão** — não espere commitar arquivos de dados
- Exceções versionadas: `apps/*/docs/modelo*.xlsx` (modelos dos coletores) e `apps/verificacao_inconsistencias/docs/*.xlsx` (referências de estrutura)
- `.opencode/`, `.antigravity/` e `.playwright-mcp/` são gitignorados (configuração/artefatos locais de agentes)

## Estado atual (2026-10-20 — operação local)

HUB com 7 apps em `apps/` — Tela Inicial + Coleta de Dados (1), Adequação (3), Verificação (1) e Unificador (1) — e 4 coletores headless (`coleta_cadastros_escolas`, `coleta_gestor`, `coleta_relatorios`, `coleta_recibos_fechamento`), sem tela. O app de Verificação de Inconsistências está implementado e verificado; o histórico completo das fases está em `docs/historico/plano_de_melhoria.md`. **Operação local (2026-10-20):** sem Docker/Caddy/TLS e sem autenticação própria do HUB; `uv sync` + `uv run streamlit run app.py --server.port <porta>`; porta escolhida a cada execução; runbook em `docs/deploy.md`. Resumo do que está no ar:

1. **Listagem "Matrículas sem CPF informado (XLSX)"** (tela Cadastro de Aluno): `rules/aluno.py` → `extrair_alunos_sem_cpf(df)` seleciona CPF `'--'`, vazio ou `NaN` (via `_normalizar`); registrada em `validations.py` como `VALIDATIONS["aluno"]["extrair_sem_cpf"]`; botão no bloco "RELATÓRIOS DE APOIO" (aviso quando não há registros).
2. **Seletor "Ano letivo"** (somente tela Aluno): `st.selectbox` de anos (decrescente, 2026→2000) salvo em `st.session_state[{prefix}ano_letivo]`; CSS do dropdown (width 5cm, max-height 360px) só nessa tela.
3. **Rótulos de botões sem prefixo "Baixar"**: "Matrículas em Duplicidade (XLSX)", "Matrículas sem CPF informado (XLSX)", "Quantitativo de Cor/Raça por Unidade Escolar" e "Quantitativo de Matrículas por Localização Diferenciada".
3.1. **Quantitativo de Matrículas por Localização Diferenciada** (tela Aluno, bloco "RELATÓRIOS DE APOIO"): `rules/aluno.py` → `levantamento_matriculas_localizacao_diferenciada(df)` conta as matrículas de cada escola pelos **parâmetros da coluna "Localização diferenciada de residência"** — "Sim" e "Não" em ordem fixa, demais valores em ordem alfabética (ignorando acentos) e "Sem informação" (vazio/`--`/`-`/NaN) por último. O XLSX (`_quantitativo_localizacao_diferenciada_xlsx`, aba `Quantitativo_Loc_Diferenciada`) traz uma linha por escola com uma coluna por parâmetro e o total de matrículas no fim; as mesmas colunas aparecem em todas as escolas. Registrado em `validations.py` como `VALIDATIONS["aluno"]["quantitativo_loc_diferenciada"]`.
4. **Validação de Alunos** (`validate_aluno`, tabela `aluno_curricular`): regras simples (zona de residência vazia; `Transporte escolar == Sim` com poder público ≠ `Municipal`) e regras de idade completas em 31/03/{ano_letivo} por período/turma (G1–G3, P1/P2, MI; creche/pré-escola/EJA/EF 9 anos) → mensagens `Sem Zona Residencial informada`, `Transporte Escolar não informado como Municipal` e `Idade incompatível com turma`; roda automaticamente após o upload; relatório modo `"aluno"` com data de nascimento, idade e INCONSISTENCIA 1..N (constantes `COL_*` em `rules/aluno.py`).
5. **Spinners de carregamento** (listagem, "RELATÓRIOS DE APOIO" e validações/relatório, com as mensagens "Carregando ..." correspondentes); totalizador ("Total de Inconsistencias"/"Total de Unidades") exibido só fora da tela Aluno.
6. **Validação de Turmas — tabela Escolarização** (`rules/turmas.py`): `read_turmas_zip` adiciona `periodo_turma`/`verifica_integral` (só escolarização); regras sigla↔etapa (`Divergência entre Sigla e Etapa`), carga `M`/`T` fora de [20h,35h] (`Carga Horária menor que 20h ou maior do que 35h.`) e integral `I` < 35h (`Integral não pode ser inferior a 35h`); relatório modo `"turma"` com colunas de contexto (etapa, carga semanal, periodo_turma, verifica_integral).
7. **Documentação completa em PDF** (Tela Inicial): `build_documentacao_pdf(logo_base64=None)` (`apps/inicio/documentacao.py`) com **reportlab==5.0.0** — capa, sumário (`TableOfContents` + `multiBuild`), rodapé paginado; download via `st.download_button` com nome datado. Detalhes reportlab 5: `TableOfContents` em `reportlab.platypus.tableofcontents`; `ParagraphStyle(parent=...)` exige instância de estilo; medidas em `reportlab.lib.units.cm`.
8. **Fase 6 — régua fina**: fim da "piscada" na troca de apps (animação `fadeIn` do banner removida); **referências de estrutura versionadas** em `apps/verificacao_inconsistencias/docs/` — a checagem de estrutura deixou de ser silenciosamente inerte; `.gitignore` ignora planilhas por padrão (exceções: modelos e referências); relatórios de inconsistências com PII são memoizados **por sessão** (sem cache global; só o agregado cor/raça mantém `st.cache_data` com `ttl=300`).
9. **Coleta do Gestor corrigida**: o vínculo é aberto por `list` → **`editing`** no modal (o código anterior exigia `visibility`, que o modal não tem); após extrair o vínculo, todos os diálogos são fechados e a Fase B espera as abas `Identificação`/`Dados pessoais` antes de extrair. Corrige a planilha que saía sem dados; regressão em `tests/test_coleta_gestor_fluxo.py` (merge `151e189`).
10. **Operação local**: HUB sobe com `uv sync` + `uv run streamlit run app.py` (sem Docker, Caddy ou TLS) e sem tela de senha; a porta é escolhida na hora e o reinício é feito pelo script externo do operador. A antiga stack de intranet (compose/OIDC/Caddy/HSTS) foi removida; a auditoria de segurança ficou restrita a métodos HTTP e exposição de arquivos.
11. **Tela da Coleta de Dados**: o relógio é um `st.container(border=True)` (chave `ca_relogio`) desenhado no estilo da referência: **layout vertical** com rótulos em maiúsculas ("Tempo em andamento", "Início da coleta"), tempo em destaque em monoespaçado azul (`#6ea8fe`, `.relogio-digital`) e data/hora em `.relogio-inicio` (dois `span` com gap). A linha da escola em coleta (`ESCOLA EM COLETA: nome (código): coletando…`, nome/código escapados com `escapar`) fica **na coluna da esquerda**, dentro do card; durante um retry por timeout ela mostra `Nome (código): nova tentativa N de 5 (timeout)…` (aviso publicado em `shared["aviso"]`, limpo quando a coleta recomeça). O botão de interromper (ou de continuar/encerrar, na pausa) fica **dentro** do card, à direita, com ícone `:material/square:` e estilo neutro (borda `#4b5563`, texto `#e5e7eb`) — exige `icon=` no `st.button` (Streamlit 1.58). O redesenho é por **`st.fragment(run_every=0.5)`** (não `sleep` + `st.rerun()`) — abortar o script no meio deixava na árvore do frontend os restos da tela anterior (Orientações e "Aplicações a coletar" reapareciam junto com a rodada). A tabela de resultados segue o desenho aprovado: `st.subheader` + cabeçalho em `st.caption` + um `st.divider()` por linha, status com bolinha colorida (🟢🟡🔴) e downloads rotulados "Baixar" (verde fosco nos dados, vermelho fosco nas pendências). Na conclusão, o card de resumo (chave `ca_resumo`) repete a mesma linguagem vertical (tempo de execução em destaque, início e término abaixo) e leva o botão **Nova rodada** à direita; a tabela usa a chave `ca_tabela` e CSS que reduz o espaço vertical entre o texto e os divisores. **Cuidado com o `margin-bottom: -1rem`** que o Streamlit aplica no container do markdown: zerar só o `p` faz o conteúdo transbordar do card — zerar o container também (regra em `TABELA_CSS`).
12. **Senha incorreta na rodada**: `login_and_read` lê a mensagem do Keycloak (`.kc-feedback-text`; o portal usa RH-SSO 7.3, tema padrão) e levanta `LoginFalhou(mensagem)`; `run_coleta` registra no log `Falha no login inicial. Abortando coleta. Motivo: <mensagem do portal>` e **levanta** a exceção (não devolve as escolas como "Falha no login"). O worker publica `shared["login_falhou"]`/`shared["login_mensagem"]`; a etapa vira `falhou` com `erro_login`, a rodada **não pausa** e a tela mostra "Login ou senha incorretos" + a mensagem do portal, com "Nova rodada" (sem "Continuar"). Login só é repetido quando o portal não exibiu mensagem (instabilidade). Testes: `test_common_session.py`, `test_common_run_coleta.py`, `test_common_ui.py`, `test_coleta_automatica_runner.py`, `test_coleta_automatica_rodada.py`.
13. **Tela de Cadastro de Turmas**: as duas etapas têm título próprio (`st.subheader`) em `apps/verificacao_inconsistencias/src/frontend.py` — **"GERAR BASE DE DADOS"** acima do grid de downloads das tabelas geradas (Relação completa, Turmas AEE, Turmas Atv Complementar, Turmas Escolarização) e **"GERAR RELATÓRIO DE INCONSISTÊNCIAS"** abaixo do divisor, acima do botão "Executar" que roda a verificação. Só a tela de Turmas recebe os títulos (as demais entradas do Gerador não têm as duas etapas); teste em `tests/test_verificacao_finalizacao.py`.
