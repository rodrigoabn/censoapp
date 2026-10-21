# Nova tentativa em timeout na Coleta Automática — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Quando uma escola falha por timeout do Playwright, a rodada da 1ª Etapa tenta de novo aquela escola — até 5 tentativas no total, 5 s entre elas — sem perder as escolas já coletadas e seguindo o algoritmo normalmente.

**Architecture:** O retry vive no `runner.py` (só a rodada). Depois de cada passada do worker, o runner separa as falhas marcadas como timeout (`"timeout": True`, preenchido pelo laço compartilhado) e roda de novo o worker **só com essas escolas**, na mesma pasta de trabalho — os arquivos das escolas que deram certo ficam no disco e entram no artefato no final. As 4 telas de coleta não mudam: as tentativas internas de navegação continuam 3; na rodada, um `ContextVar` as reduz para 1, porque lá o retry é por escola.

**Tech Stack:** Python 3.13, Playwright (sync), Streamlit, pytest, ruff, uv.

**Spec:** decisões do usuário na sessão de 2026-10-21 (perguntas respondidas): só na rodada; todos os timeouts do Playwright; 5 tentativas no total; 5 s fixos; retry interno reduzido só na rodada.

## Global Constraints

- Nunca apagar coletas já concluídas: a passada de retry recebe **apenas** as escolas que falharam por timeout.
- Máximo de **5 tentativas no total** por escola (`MAX_TENTATIVAS_TIMEOUT = 5`), com **5.0 s** fixos entre uma passada e a próxima.
- Falha que **não** é timeout não repete (escola não encontrada, recibo indisponível, relatório inexistente, preenchimento não iniciado, coleta interrompida).
- As 4 telas de coleta seguem com 3 tentativas de navegação (nada muda para elas).
- A interrupção do usuário vence a espera: `stop_event.wait(5.0)` e a rodada encerra.
- Comentários, mensagens e testes em português; sem PII nos logs.

## Review Focus

- Portal fora do ar: a escola falha 5× e entra em pendências com o motivo do erro — a rodada não pode travar nem duplicar a escola no XLSX de pendências.
- `Page.goto`/`click`/download estourando: a falha também é marcada como timeout (o motivo contém `Timeout ... exceeded`).
- Falha no **login** por timeout: todas as escolas da passada são marcadas com `"timeout": True` e a rodada repete a passada.
- Interrupção durante os 5 s de espera: a etapa é marcada `interrompida`, o parcial fica salvo e o pacote completo não é gerado.
- Retry com sucesso: a escola repetida entra no artefato e **sai** das pendências; a que nunca falhou não é recoletada.

---

### Task 1: Retry por escola no runner da rodada

**Files:**
- Modify: `apps/coleta_automatica/src/runner.py` (`_executar_etapa`, constantes, `e_falha_timeout`)
- Test: `tests/test_coleta_automatica_runner.py`

**Interfaces:**
- Produces: `MAX_TENTATIVAS_TIMEOUT: int = 5`, `ESPERA_ENTRE_TENTATIVAS: float = 5.0`, `e_falha_timeout(falha: dict) -> bool`; `estado["tentativa"]` e `estado["tentativa_escolas"]` publicados durante a rodada.

- [ ] **Step 1:** testes que falham: repete só as escolas com timeout; desiste na 5ª; não repete erro comum; espera 5.0 s; interrupção na espera encerra a etapa; `e_falha_timeout` reconhece as mensagens do Playwright.
- [ ] **Step 2:** `uv run python -m pytest tests/test_coleta_automatica_runner.py -q` → falha (sem `e_falha_timeout`/sem repetição).
- [ ] **Step 3:** implementar o laço de passadas em `_executar_etapa` (zera `current/last/error/done/failures` a cada passada, preserva `count`, acumula os pendentes por código — `pendentes` guarda a última falha de **todas** e `retentaveis` só as de timeout, para a falha comum não sumir do XLSX de pendências —, `stop_event.wait(5.0)`).
- [ ] **Step 4:** repetir o passo 2 → passa.

### Task 2: Marcar a falha como timeout no laço compartilhado

**Files:**
- Modify: `apps/common/coleta.py` (`e_timeout`, dicionários de falha)
- Test: `tests/test_common_run_coleta.py`

**Interfaces:**
- Produces: `e_timeout(exc: BaseException) -> bool`; toda falha de escola passa a carregar `"timeout": bool`.

- [ ] **Step 1:** testes que falham: `PlaywrightTimeoutError` no `scrape_one` → `"timeout" is True` e motivo `Erro: ...`; `ValueError` → `"timeout" is False`; timeout no login inicial → todas as escolas com `"timeout": True` e motivo `Falha no login`.
- [ ] **Step 2:** rodar → falha.
- [ ] **Step 3:** implementar `e_timeout` e preencher `"timeout"` nos 5 pontos de falha (login, re-login antes/depois, exceção mapeada = False, exceção genérica).
- [ ] **Step 4:** rodar → passa.

### Task 3: Tentativas de navegação por contexto (1 na rodada, 3 nas telas)

**Files:**
- Modify: `apps/common/session.py` (`TENTATIVAS_NAVEGACAO`, `tentativas_navegacao`, `select_school`), `apps/coleta_cadastros_escolas/src/scraper.py` e `apps/coleta_gestor/src/gestor_scraper.py` (`_open_school_ficha`), `apps/coleta_automatica/src/runner.py` (set/reset)
- Test: `tests/test_common_session.py`, `tests/test_coleta_esperas.py`

**Interfaces:**
- Produces: `session.TENTATIVAS_NAVEGACAO: ContextVar[int]` (default 3) e `session.tentativas_navegacao() -> int`; `select_school(..., tentativas: int | None = None)` e `_open_school_ficha(..., tentativas: int | None = None)` leem o contexto quando o argumento é `None`.

- [ ] **Step 1:** testes que falham: `select_school` faz 3 navegações por padrão e 1 com o contexto em 1; `_open_school_ficha` idem.
- [ ] **Step 2:** rodar → falha.
- [ ] **Step 3:** implementar o `ContextVar` e o `set(1)`/`reset` em volta do worker no runner.
- [ ] **Step 4:** rodar → passa.

### Task 4: Aviso da nova tentativa no cartão do relógio

**Files:**
- Modify: `apps/coleta_automatica/src/frontend.py` (`_cartao_relogio`)
- Test: `tests/test_coleta_automatica_rodada.py`

- [ ] **Step 1:** teste que falha: com `estado["tentativa"] == 2` e `tentativa_escolas == 1`, o cartão mostra "Nova tentativa 2 de 5" e não mostra a linha na primeira passada.
- [ ] **Step 2:** rodar → falha.
- [ ] **Step 3:** implementar a linha (só quando `tentativa > 1`).
- [ ] **Step 4:** rodar → passa.

### Task 5: Documentação

**Files:**
- Modify: `AGENTS.md` (Convenções de scraping)

- [ ] **Step 1:** acrescentar a convenção: timeout do Playwright na rodada → retry por escola (5 no total, 5 s), com as coletas já feitas preservadas; as telas individuais mantêm 3 tentativas de navegação.
- [ ] **Step 2:** `uv run ruff check .` e `uv run python -m pytest -q` → tudo verde.
