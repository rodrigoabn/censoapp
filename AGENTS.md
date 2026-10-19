# Guia do Agent — Aplicações de Apoio Censo Escolar

## Comandos principais

```bash
uv run streamlit run app.py                         # inicia o HUB (local)
uv run python -m pytest                             # suíte offline (segurança pulada sem SECURITY_LIVE=1)
uv run ruff check .                                 # lint (config no pyproject)
SECURITY_LIVE=1 uv run python -m pytest tests/security/  # auditoria ao vivo (alvo: ver "Testes")
uv add <pacote>                                     # adicionar dependência

docker compose up -d --build                        # intranet: app + Caddy (runbook: docs/deploy.md)
docker compose logs -f app                          # logs ao vivo; arquivo em ./logs/censoapp.log
```

## Arquitetura

- **Entrypoint**: `app.py` — HUB Streamlit com navegação lateral
- **10 apps** em `apps/`, cada uma autocontida, + código compartilhado em `apps/common/` (`auth`, `browser`, `coleta`, `export`, `school_list`, `session`, `ui`):
  - `inicio/` — página inicial + documentação completa em PDF
  - `coleta_cadastros_escolas/` — raspa dados de escolas do Educacenso → XLSX (6 abas)
  - `coleta_gestor/` — raspa dados de gestores → XLSX (3 abas)
  - `coleta_relatorios/` — baixa relatórios CSV (turmas/alunos/profissionais) → ZIP
  - `coleta_recibos_fechamento/` — baixa recibos PDF → ZIP
  - `adequacao_turmas/` — converte o ZIP de turmas no layout padronizado → ZIP
  - `adequacao_alunos/` — converte o ZIP de alunos no layout padronizado → ZIP
  - `adequacao_profissionais/` — converte o ZIP de profissionais no layout padronizado → ZIP
  - `verificacao_inconsistencias/` — aponta inconsistências nos ZIPs/planilhas (regras em `src/rules/`) → XLSX
  - `unificador_inconsistencias/` — unifica os relatórios de inconsistências por unidade escolar → XLSX
- **As coletas seguem o mesmo padrão**: `auth.py` + scraper + `frontend.py` + exporter/zipper + `modelo.py`; a lista de escolas vem de `apps/common/school_list.py`
- **Templates de modelo**: `apps/coleta_cadastros_escolas/docs/modelo_coleta.xlsx` (6 abas) e `apps/coleta_gestor/docs/modelo_coleta_gestor.xlsx` (3 abas); referências de estrutura (só cabeçalho) em `apps/verificacao_inconsistencias/docs/`

## Convenções de scraping

- **Sempre usar `playwright.sync_api`** (nunca async)
- **`READ_ONLY = True`** em todo `auth.py` — jamais escrever dados no Educacenso
- **Fluxo de login**: Keycloak em `acesso.inep.gov.br`, CPF + senha
- **Hierarquia de exceções**: `SessaoExpirada`, `LoginFalhou`, `ReciboIndisponivel`, `PreenchimentoNaoIniciado`
- **Logs personalizados em português** (`logger = logging.getLogger("coleta_*")`)
- **Reuso de sessão com retry**: `run_scraping()` mantém um browser context, refaz login se expirar
- **Arquivos temporários**: cada execução cria uma pasta exclusiva (`nova_pasta_temporaria()`, prefixos `educacenso_*_tmp_`) em `/tmp` para os CSVs/PDFs da coleta; a consolidação (`build_xlsx`/`build_zip`) remove a pasta no final

## Entrada/Saída de dados

- **Entrada**: XLSX com colunas `código do inep` + `nome da unidade` (tolera maiúsculas/minúsculas via `apps/common/school_list.py`)
- **Saída de dados de escolas**: XLSX único com 6 abas, construído via `exporter.py` (CSV → openpyxl)
- **Saída de relatórios**: ZIP de CSVs via `zipper.py`
- **Saída de recibos**: ZIP de PDFs via `zipper.py`

## Ambiente e secrets

- **Credenciais**: `apps/coleta_cadastros_escolas/docs/credenciais.json` (gitignored)
- **`.streamlit/secrets.toml`** (gitignored) — no container é montado **somente-leitura** em `/app/.streamlit/`; exemplo comentado em `.streamlit/secrets.toml.example`
- **Dependências de sistema para Playwright** em `packages.txt` (libnss3, libnspr4, etc.)
- Chromium instalado automaticamente na primeira execução via `playwright install chromium` (ver `_ensure_chromium()`); na imagem Docker ele já vem embutido

## Implantação (intranet) — Fase 2

- **Runbook completo**: `docs/deploy.md` (TLS interno do Caddy, secrets, cabeçalhos/CSP, testes de segurança, troubleshooting).
- **Compose**: `docker-compose.yml` — app Streamlit + proxy `caddy`; copie `.env.example` → `.env`. `./logs` e `.streamlit/secrets.toml` são montados como volumes (o arquivo de secrets **precisa existir antes do primeiro `up`**, senão o Docker cria um diretório no lugar; crie `logs/` com uid 1000 — se não for gravável, o log cai para o stderr e o HUB segue no ar).
- **Autenticação** (`auth_gate.py`, chamado no topo do `app.py`, antes de qualquer render): modo detectado pela config e forçável por `CENSO_AUTH_MODE`:
  - `oidc` — seção `[auth]` nos secrets (SSO via `st.login`); **fecha por padrão** se forçado sem `[auth]`;
  - `senha` — seção `[auth_simples]` (senha única compartilhada; fallback enquanto não houver OIDC);
  - `aberto` — sem secrets (uso local; mostra aviso na sidebar).
- **Logging** (`logging_setup.py`, idempotente a cada rerun): arquivo rotativo `censoapp.log` (5 MB × 5) em `CENSO_LOG_DIR` (no container: `/app/logs`); nunca registrar PII.
- **CI**: `.github/workflows/ci.yml` (push/PR → `uv sync --frozen` + `ruff check .` + `pytest -q`).

## Testes

- `tests/` cobre a suíte offline (fakes, sem rede): `uv run python -m pytest` → 660 passed / 33 skipped; lint com `uv run ruff check .`
- `tests/security/` é ao vivo; **os 33 testes de segurança são pulados por padrão** — exigem `SECURITY_LIVE=1`
- Alvo via `SECURITY_TARGET` (**obrigatório** — sem padrão; ex.: `https://censo.seduct.intra/`); com TLS interno, use `REQUESTS_CA_BUNDLE` apontando para a CA do Caddy
- Não intrusivos: poucas requisições, sem fuzzing/brute-force
- Níveis: "app" vs "plataforma" nos achados

## .gitignore — Atenção

- `*.xlsx`, `*.xls`, `*.csv`, `*.log` são **gitignorados por padrão** — não espere commitar arquivos de dados
- Exceções versionadas: `apps/*/docs/modelo*.xlsx` (modelos dos coletores) e `apps/verificacao_inconsistencias/docs/*.xlsx` (referências de estrutura)
- `.opencode/` é gitignorado (configuração local de agentes)

## Estado atual (2026-10-19)

HUB com 10 apps (Coleta, Adequação, Verificação e Unificador) + Tela Inicial. O app de Verificação de Inconsistências está implementado e verificado; o histórico completo das fases está em `docs/plano_de_melhoria.md`. Resumo do que está no ar:

1. **Listagem "Matrículas sem CPF informado (XLSX)"** (tela Cadastro de Aluno): `rules/aluno.py` → `extrair_alunos_sem_cpf(df)` seleciona CPF `'--'`, vazio ou `NaN` (via `_normalizar`); registrada em `validations.py` como `VALIDATIONS["aluno"]["extrair_sem_cpf"]`; botão no bloco "RELATÓRIOS DE APOIO" (aviso quando não há registros).
2. **Seletor "Ano letivo"** (somente tela Aluno): `st.selectbox` de anos (decrescente, 2026→2000) salvo em `st.session_state[{prefix}ano_letivo]`; CSS do dropdown (width 5cm, max-height 360px) só nessa tela.
3. **Rótulos de botões sem prefixo "Baixar"**: "Matrículas em Duplicidade (XLSX)", "Matrículas sem CPF informado (XLSX)" e "Quantitativo de Cor/Raça por Unidade Escolar".
4. **Validação de Alunos** (`validate_aluno`, tabela `aluno_curricular`): regras simples (zona de residência vazia; `Transporte escolar == Sim` com poder público ≠ `Municipal`) e regras de idade completas em 31/03/{ano_letivo} por período/turma (G1–G3, P1/P2, MI; creche/pré-escola/EJA/EF 9 anos) → mensagens `Sem Zona Residencial informada`, `Transporte Escolar não informado como Municipal` e `Idade incompatível com turma`; roda automaticamente após o upload; relatório modo `"aluno"` com data de nascimento, idade e INCONSISTENCIA 1..N (constantes `COL_*` em `rules/aluno.py`).
5. **Spinners de carregamento** (listagem, "RELATÓRIOS DE APOIO" e validações/relatório, com as mensagens "Carregando ..." correspondentes); totalizador ("Total de Inconsistencias"/"Total de Unidades") exibido só fora da tela Aluno.
6. **Validação de Turmas — tabela Escolarização** (`rules/turmas.py`): `read_turmas_zip` adiciona `periodo_turma`/`verifica_integral` (só escolarização); regras sigla↔etapa (`Divergência entre Sigla e Etapa`), carga `M`/`T` fora de [20h,35h] (`Carga Horária menor que 20h ou maior do que 35h.`) e integral `I` < 35h (`Integral não pode ser inferior a 35h`); relatório modo `"turma"` com colunas de contexto (etapa, carga semanal, periodo_turma, verifica_integral).
7. **Documentação completa em PDF** (Tela Inicial): `build_documentacao_pdf(logo_base64=None)` (`apps/inicio/documentacao.py`) com **reportlab==5.0.0** — capa, sumário (`TableOfContents` + `multiBuild`), rodapé paginado; download via `st.download_button` com nome datado. Detalhes reportlab 5: `TableOfContents` em `reportlab.platypus.tableofcontents`; `ParagraphStyle(parent=...)` exige instância de estilo; medidas em `reportlab.lib.units.cm`.
8. **Fase 6 — régua fina (concluída)**: fim da "piscada" na troca de apps (animação `fadeIn` do banner removida); **referências de estrutura versionadas** em `apps/verificacao_inconsistencias/docs/` — a checagem de estrutura deixou de ser silenciosamente inerte; `.gitignore` ignora planilhas por padrão (exceções: modelos e referências); relatórios de inconsistências com PII são memoizados **por sessão** (sem cache global; só o agregado cor/raça mantém `st.cache_data` com `ttl=300`).
