# Plano de Melhoria — HUB de Apoio ao Censo Escolar (censoapp)

> **Documento vivo de acompanhamento.** Marque `[x]` conforme cada item for concluído (`[~]` = em andamento).
> **Revisão completa de 2026-10-18** feita com 4 auditorias em paralelo: (1) cobertura de testes das regras → Fase 3; (2) duplicação entre apps → Fase 4; (3) hotspots de tempo dos 4 coletores → Fase 5; (4) limpezas/docs/PII → Fase 6.
> Referências de linha são da data da revisão (podem deslocar).

**Estado base (2026-10-18):** `master @ c37aa4f` · **20 commits à frente do `origin`** (sem push) · suíte **83 passed / 33 skipped** · `ruff` limpo · Docker parado · auth em modo `senha`.

---

## Sumário

| Fase | Tema | Esforço | Status |
|---|---|---|---|
| ✅ 1 | Hotfixes P0/P1 | — | **concluída** |
| ✅ 2 | Intranet + auth + CI/logging | — | **concluída** |
| 🔜 5 | Eficiência da coleta | dias–1 semana | **próxima** (preferida) |
| 3 | Testes golden das regras | 1–2 semanas | pendente |
| 4 | Refatoração `apps/common` | semanas | pendente (maior risco) |
| 6 | Régua fina | dias | pendente |
| E | Extras: hospedagem / operação | — | pendente |

**Ordem sugerida:** **5 → 3 → 4 → 6 → extras**. Alternativa técnica original: 3 → 4 → 5 → 6. A inversão é segura porque os ganhos da Fase 5 são localizados por app; o refactor da Fase 4 reabsorve depois.

## Como executar (regras de sempre)

- Cada fase ganha um **plano detalhado (TDD)** no início da execução: tasks pequenas, 1 commit por task, suíte verde antes do commit, revisão por subagente no fim — como nas Fases 1–2 (planos em `~/.opencode/plans/`).
- Invariantes do projeto: `READ_ONLY=True` intocado · sem PII em logs · UI/mensagens em PT-BR · testes herméticos (sem rede/portal) · `uv run ruff check .` + `uv run python -m pytest -q` verdes por task · **sem push** · `git add` explícito · nunca commitar dados (xlsx/csv/log/zip) nem segredos.
- Gate por app migrado (Fase 4): lote fixo de 2–3 escolas + **comparação semântica** saída antiga × nova (não byte a byte).

---

## Fase 5 — Eficiência da coleta ✅ (5.0–5.7 feitos; 5.8 pendente — execução do usuário com o portal)

**Objetivo:** cortar o desperdício controlável do tempo por escola (estimado **10–25 s/escola**; até ~40 s no gestor; baseline: 222 escolas × 2–3 h por coletor) e **medir** antes/depois.
**Recon: CONCLUÍDO** (auditoria de 2026-10-18 — hotspots mapeados abaixo).
**Pronto quando:** timing instrumentado; ganhos medidos no protocolo antes/depois; suíte verde; saídas equivalentes.

- [x] **5.0 — Timing por escola (P0, pré-requisito).** `t0=time.monotonic()` antes de cada escola; log `[codigo] ok/erro em Xs`; contadores (networkidle estourado, re-logins, retries de abertura). *4 scrapers.*
- [x] **5.1 — Sigilo rápido (P1).** `wait_for_selector("mat-dialog-container", timeout=1500)`; se ausente → segue direto; se presente → manter rolagem, aceitar e esperar o modal **sumir** (`state="detached"`) em vez de `wait_for_timeout(3000)`; fallback para o wait longo se a ficha não abrir. **Ganho: ~6,5 s/escola; gestor ~19,5 s** (3 chamadas de sigilo). *`scraper.py:243-263`, `gestor_scraper.py:201-221`, `report_scraper.py:131-150`, `receipt_scraper.py:135-154`.*
- [x] **5.2 — Cache do modelo XLSX (P3).** `functools.cache` em `load_model()` + `norm_map` por aba. **Ganho: ~22 s/run (cadastros) + I/O.** *`modelo.py` ×2; remove recargas em scrapers/exporters.*
- [x] **5.3 — `networkidle` fora (P2).** Remover/reduzir (o `wait_for_selector` do input já é o gate real); logar quando estourar. *Cadastros `scraper.py:282-285`, Relatórios `report_scraper.py:165-168`, Recibos `receipt_scraper.py:169-172`.*
- [x] **5.4 — Escrita incremental + retomada (P4).** Callback `on_school_done`; frontends gravam CSV/PDF por escola (hoje: crash perde **o lote inteiro**); bônus: pular códigos já presentes no tmp (retomada); corrigir docstrings dos exporters ("appendada durante a raspagem" é falso hoje).
- [x] **5.5 — Gestor: não repetir a pesquisa (P5).** Fase B reaproveita a lista já carregada (edit direto), fallback = reload; sleeps de `_extract_with_retry` → poll curto. **Ganho: 4–12 s (+0–6 s).** *`gestor_scraper.py:495-600`.*
- [x] **5.6 — Recibos: poll único (P6).** Loop 15×(1 s + loader) → 1 `wait_for_selector` com seletor-união (15 s). *`receipt_scraper.py:251-261`.*
- [x] **5.7 — Throttle configurável (P7).** `CENSO_SLEEP_ESCOLAS` (default 0.3 s) nos 4 loops.
- [ ] **5.8 — Protocolo antes/depois.** Planilha fixa de ~10 escolas (normal, "não encontrada", fechada) × 3 execuções antes e depois; comparar mediana s/escola + total; conferir saída equivalente (linhas por aba + amostra); registrar no doc da fase.
- [ ] **5.9 — (Opcional) Paralelismo piloto.** **P8:** workers por **processo** (cada um com seu `sync_playwright` + context + login + tmp próprio) atrás de flag `WORKERS` — **ou** **P9** operacional: rodar os 4 coletores em paralelo. **Risco alto:** Keycloak single-session (tempestade de re-login) + rate limit → só com piloto de 2 sessões × 10 escolas e log de re-login. Default continua 1.

**Status da Fase 5 (2026-10-18):** **5.0–5.7 implementados** na worktree `fase5-eficiencia-coleta` (commits `fase 5.0`–`fase 5.7`; suíte **124 passed / 33 skipped**; ruff limpo). **5.8 pendente** — protocolo antes/depois com o portal (execução do usuário). Bônus de retomada do **5.4 não feito** (dados parciais ficam em `/tmp/educacenso_*_tmp_*` para recuperação manual). **5.9 adiado** (decisão do ciclo; risco Keycloak single-session).

**Observações:** `expect_download(60 s)` (geração no portal) é irredutível no cliente — o limite de ganho em Relatórios é menor; a cauda (retry de 30 s do campo de código) deve ser **medida antes** de mexer; `_wait_loader` do gestor tem teto de 15 s (vs 6 s) — não é o ganho médio, é a cauda.

**Foco da revisão:** nenhuma otimização pode alterar dados coletados (comparar amostras); fallback do sigilo obrigatório; paralelismo nunca default.

---

## Fase 3 — Testes golden das regras

**Objetivo:** rede de segurança para as regras de verificação **antes** de qualquer refatoração.
**Estado hoje:** 116 itens coletados; apenas 13 tocam verificação/unificador; **nenhum teste exercita `rules/`**.
**Pronto quando:** cada regra nomeada tem caso positivo + negativo; estimativa: **~198 itens novos** (P0 = 144, P1 = 54), em ~35 funções parametrizadas.

- [ ] **3.1 — `tests/rules/conftest.py`.** Fixtures `wb_bytes(sheets)` (openpyxl; nomes ≤ 31 chars) e `df(rows)` + constantes importadas dos próprios módulos (não redigitar cabeçalhos).
- [ ] **3.2 — `tests/rules/test_unidades.py` (37).** 5 abas válidas; 26 negativos; 5 abas ausentes; bytes inválidos.
- [ ] **3.3 — `tests/rules/test_gestor.py` (28).** 3 abas válidas; 21 negativos; 3 abas ausentes; bytes inválidos.
- [ ] **3.4 — Turmas (28).** `test_turmas_curricular.py` (18: linha válida, 15 negativos, colunas especiais, dedup) + `test_turmas_escolarizacao.py` (10: sigla↔etapa, MI, cargas M/T/I, merge).
- [ ] **3.5 — Aluno (31).** `test_aluno_validacao.py` (16: 12 ramos de idade, 31/03 vs 01/04, `ano_letivo=None`, dedup) + `test_aluno_listagens.py` (15: duplicadas, sem CPF, cor/raça + agregação).
- [ ] **3.6 — `tests/rules/test_profissionais.py` (13).** 8 negativos; isenção de apoio (2); agrupamento/dedup (2); placeholders `-`.
- [ ] **3.7 — `tests/rules/test_validations.py` (7).** 5 chaves do dispatcher; `expected_columns`; helpers de aluno.
- [ ] **3.8 — P1: `test_upload.py` (16) + `test_checar_estrutura.py` (5).** Contrato de entrada (BOM/`;`/linha-título, splits, colunas derivadas).
- [ ] **3.9 — P1: extras do unificador/adequação (28).** `_normalize_inep` decimal, `_read_report` multi-abas, categorias desconhecidas, `_safe_filename` (10) + processors de adequação ×3 apps + helpers duplicados (18).
- [ ] **3.10 — P1: `test_verificacao_frontend_modes.py` (5).** `_modo_relatorio` (5 configs) + `_build_xlsx` modos `turma`/`aluno`/`profissional`.

**Armadilhas (da auditoria — usar nas fixtures):** idade em **31/03** (`aluno.py:48-52`); `pd.to_datetime(dayfirst=True)` interpreta **ISO errado** — usar `dd/mm/yyyy`; cabeçalhos casam **string exata** (en-dash e typos: `"3 – localizacaoZona"`, `"7b -Término (previsão)"`); abas ≤ 31 chars; **aba vazia causa early-return** em `validate_unidades` (fixtures com ≥1 linha em todas as 5 abas); valores viram `str()` — gravar texto, não datas do Excel; usar `dtype=str` (CPF float → `"…0"` é descartado); `validate_profissionais` tem **falso positivo** com coluna ausente (`:42-46` — se virar comportamento testado, decidir se corrige na fase).

**Foco da revisão:** fidelidade das fixtures ao formato real do Educacenso (typos inclusos); testes não devem "consertar" as regras — só congelar o comportamento atual.

---

## Fase 4 — Refatoração `apps/common` (sem mudança de comportamento)

**Objetivo:** eliminar **~2.400–2.700 linhas duplicadas**; módulos `apps/common/{auth, school_list, session, browser, export, ui}.py`; **piloto: Relatórios** (menor atrito — similaridade 0,78/0,91 com Recibos).
**Pronto quando:** 4 coletores + verificação consumindo os comuns; hack de `sys.path` removido; suíte verde; saídas equivalentes por app.

- [ ] **4.1 — `apps/common/auth.py`.** `BASE_URL`, `READ_ONLY`, `assert_read_only()`; os 4 `auth.py` viram re-export.
- [ ] **4.2 — `apps/common/school_list.py`.** `_find_column` + `read_school_list` (verificação passa alias `"unidade escolar"` e não exige nome).
- [ ] **4.3 — `apps/common/session.py` + `browser.py`** (extraídos do Relatórios, quase 1:1): `login_and_read`, `accept_sigilo_if_present`, `select_school(after_select=…)`, `marcar_nao_processadas`, `LoginFalhou`/`SessaoExpirada`; `safe_cleanup`, `wait_loader`, `session_expirada`, `raise_if_expired`. **Manter wrappers** com os nomes antigos no módulo do app (monkeypatch dos testes).
- [ ] **4.4 — `apps/common/export.py` + `run_coleta` genérico.** Temporários, "não coletadas", ZIP/XLSX; loop com `scrape_one` + mapa exceção→motivo + `accept_downloads` (wrapper preserva assinatura pública).
- [ ] **4.5 — `apps/common/ui.py`.** `SUBMIT_CSS`, chromium, `init_state`/`monitor`/`finalize`/worker/start parametrizados pelo dict de config; `render_report_frontend(config, logo)` intacto.
- [ ] **4.6 — Migrar Recibos** (valida parametrização CSV↔PDF nos mesmos módulos).
- [ ] **4.7 — Migrar Gestor + Cadastros.** Remove o hack de `sys.path` (`app.py:12-18`, `tests/conftest.py:12-14`) e imports `src.*` → relativos.
- [ ] **4.8 — Verificação** consome `school_list`/`export` (sem fundir `_load_structure` linha-1 com `load_model` linha-2).

**Riscos mapeados (resumo dos 18):** chaves `session_state` prefixadas (`rt_`/`ra_`) vs literais (`ws_`/`cg_`); **mensagens assertadas em testes** (`"Falha no login"`, `"Escola não encontrada"`, `"Coleta interrompida (não processada)"`, `"Erro (re-login):"`…); timeouts divergentes (gestor `_wait_loader` 15 s; `_open_school_ficha` goto 30 s vs 15 s); sigilo do gestor restrito a `mat-dialog-container`; `_ensure_chromium` ausente no Relatórios; **3 formatos de nome de arquivo** (`cadastro_escola_educacenso_*`, `vinculo_gestor_educacenso_*`, `{prefix}_educacenso_*` e recibos **sem** "educacenso"); prefixos de tmp exigidos por teste; logger por app (não fixar 1); re-login com formatos de motivo diferentes (`{exc}` vs `{str(exc) or type(exc).__name__}`).

**Foco da revisão:** zero mudança de comportamento observável (mensagens/chaves/nomes de arquivo/nº de abas); gate de comparação semântica por app migrado; monkeypatches sobrevivem.

---

## Fase 6 — Régua fina

- [ ] **6.1 — "Pisca" na troca de apps.** Causa provável: **replay da animação CSS** `fadeIn 0.7s` do `.title-container` (`app.py:347`) quando o banner é recriado na troca; secundária: banners da página anterior durante o rerun; e um caso real: `st.success` imediatamente antes de `st.rerun()` (`verificacao/frontend.py:735-739`). Opções: (a) remover a animação; (b) remover o `st.rerun()` da nav (`app.py:653`); (c) remover o `st.success` redundante. (`st.fragment` **não** se aplica à troca de páginas.) Testar cada opção isolada.
- [ ] **6.2 — `checar_estrutura`/`_REFERENCIA_BYTES`: DECISÃO EM ABERTO.** Hoje silenciosamente inerte (`verificacao/frontend.py:22-40`, `:741-748`; pasta `arquivos de teste/` não existe no git). Opções: **(a)** versionar referências sintéticas só-cabeçalho em `apps/verificacao_inconsistencias/docs/` (+ teste "referência carrega"; ponto de manutenção quando o layout mudar) **ou (b)** remover o recurso (+ `checar_estrutura.py`). Mínimo: logar "checagem desativada" enquanto decidir.
- [ ] **6.3 — `_status_color`: ramo morto.** Remover `or estado.startswith("Falha no login")` em `coleta_relatorios/src/frontend.py:267` e `coleta_recibos_fechamento/src/frontend.py:299` (o login falho nunca passa por `on_progress`).
- [ ] **6.4 — `.gitignore`.** Adicionar `*.xlsx`/`*.xls` + negações `!apps/*/docs/modelo*.xlsx` (os 2 modelos rastreados não são afetados; corrige claims falsos no AGENTS.md e no PDF).
- [ ] **6.5 — `AGENTS.md` (reescrever seção de estado).** Corrigir: "5 apps" → 10; caminhos dos modelos; `sheets.py` **não existe** (remover menção); `.opencode/agents/*` **não existem**; gitignore de xlsx; refs de linha defasadas (`app.py:347`/`646-653`/`673-683`); "Estado atual" de 2026-08-04 → atual; contagem de testes.
- [ ] **6.6 — PDF de documentação (`apps/inicio/documentacao.py`).** "6 testes" → suíte offline completa (83+33); incluir comandos da suíte offline (seção 3.3); tabela Visão Geral omite o grupo **Adequação** (3 linhas + subseção); caminhos dos modelos; alvo legado `censoescolar.streamlit.app` (alinhar com `tests/security/conftest.py:29`); claim de gitignore; menção a Google Sheets.
- [ ] **6.7 — Política de cache PII (`st.cache_data` ×5, todos globais sem TTL).** Mínimo: `ttl` curto (300–900 s) nos 5; alvo LGPD: memoizar em `st.session_state` os 4 com PII e manter cache só do agregado. *`verificacao/frontend.py:72,116,195,224,253`.*

**Foco da revisão:** cada item é independente; nada de mudança de comportamento fora do descrito; decisões (6.2/6.7) registradas no commit.

---

## Extras

### Hospedagem (testar na máquina de dev; máquina desliga fora de sessão)

- [ ] **E1 — Cloudflare quick tunnel (sem domínio).** Instalar `cloudflared` (apt), subir a stack local (`CADDY_HTTP_PORT=8080`), apontar o túnel para `http://localhost:8080` e testar do 4G; validar gate `senha` + CSP/websocket. *(Atenção: conferir se o Caddy na :8080 responde direto ou redireciona — ajustar o upstream do túnel.)*
- [ ] **E2 — Oracle Always Free (opcional, depois).** Criar conta (cartão) e VM ARM 2 OCPU/12 GB em São Paulo; repetir o `docker compose` do runbook; avaliar reclaim por inatividade.

### Operação (fora do código)

- [ ] **E3 — Apagar `credenciais.json` da raiz** (usuário; lembrete ativo).
- [ ] **E4 — Despublicar o Streamlit Cloud** (checklist §9 de `docs/deploy.md`).
- [ ] **E5 — Push dos 20 commits** para `origin/master` (CI passa a rodar no GitHub; só a pedido).
- [ ] **E6 — Deploy real na SEDUCT** (dia da implantação): domínio real + `[auth]` OIDC + CA do Caddy + firewall — runbook cobre.

---

## Concluído (histórico)

- [x] **Fase 1 — Hotfixes P0/P1** (8 itens: temporários isolados, interrupção na troca de página, escolas "não coletadas", sessão expirada no download, escape HTML, neutralização de fórmulas, reportlab/devcontainer) — mesclada.
- [x] **Fase 2 — Intranet + autenticação + CI/logging** (Docker+compose+Caddy/TLS, `auth_gate` oidc/senha/aberto, CI pytest+ruff, logging rotativo sem PII, runbook `docs/deploy.md`) — mesclada (`c37aa4f`).
- [x] **Revisão completa do plano** com 4 auditorias (2026-10-18) — este documento.

## Fora de escopo (decidido)

Reescrita FastAPI/React · `sync→async` do Playwright · APIs internas do portal · Polars/duckdb · WeasyPrint/Typst · SPA · **Histórico/BI** (próxima onda, não selecionado).

## Decisões em aberto

1. **6.2** — referências de estrutura: versionar amostras sintéticas × remover o recurso.
2. **6.7** — PII no cache: `ttl` curto (mínimo) × `session_state` (alvo).
3. **Fase 4** — preservar wrappers/monkeypatch antigos × adaptar testes junto (muda o "sem mudança de comportamento" para "sem mudança de comportamento + testes ajustados mecanicamente").
4. **Ordem das fases** — sugerida 5 → 3 → 4 → 6; confirmar na largada de cada uma.
