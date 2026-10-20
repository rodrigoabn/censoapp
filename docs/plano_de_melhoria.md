# Plano de Melhoria — HUB de Apoio ao Censo Escolar (censoapp)

> **Documento vivo de acompanhamento.** Marque `[x]` conforme cada item for concluído (`[~]` = em andamento).
> **Revisão completa de 2026-10-18** feita com 4 auditorias em paralelo: (1) cobertura de testes das regras → Fase 3; (2) duplicação entre apps → Fase 4; (3) hotspots de tempo dos 4 coletores → Fase 5; (4) limpezas/docs/PII → Fase 6.
> Referências de linha são da data da revisão (podem deslocar).

**Estado base (2026-10-18 — revisão; histórico):** `master @ c37aa4f` · suíte **83 passed / 33 skipped** · Docker parado · auth em modo `senha`.
**Estado atual (2026-10-20 — operação local):** Fases 1–6 mergeadas (`9f880ac`; hotfix do gestor `151e189`; correção da finalização da verificação `8df55fb`) · suíte **655 passed / 19 skipped** · `ruff` limpo · **operação local (E6 redefinida):** sem Docker/Caddy e sem TLS por padrão, sem autenticação própria; `uv sync` + `uv run streamlit run app.py --server.port <porta>` (porta escolhida a cada execução), runbook em `docs/deploy.md` · **Python 3.14** (`da8f048`) · `origin/master` em `b5611ef` (operação local publicada; último commit: `.gitignore` de artefatos do Playwright MCP) · hospedagem: somente rede interna da SEDUCT.

---

## Sumário

| Fase | Tema | Esforço | Status |
|---|---|---|---|
| ✅ 1 | Hotfixes P0/P1 | — | **concluída** |
| ✅ 2 | Intranet + auth + CI/logging | — | **concluída** (histórico; substituída pela operação local em 2026-10-20) |
| ✅ 5 | Eficiência da coleta | dias–1 semana | **concluída** (5.0–5.8; 5.9 adiado) |
| ✅ 3 | Testes golden das regras | 1–2 semanas | **concluída** |
| ✅ 4 | Refatoração `apps/common` | semanas | **concluída** (4.1–4.8; gates ao vivo 1–4 aprovados) |
| ✅ 6 | Régua fina | dias | **concluída** (6.1–6.7; gate aprovado 2026-10-20; merge `9f880ac`) |
| ✅ E | Extras: operação local (uv) | — | **concluída** (E6; E3 segue em espera) |

**Ordem sugerida:** 5 ✅ → 3 ✅ → 4 ✅ → **6 ✅ → extras** (régua fina concluída — 6.1–6.7; gate aprovado em 2026-10-20). Alternativa técnica original: 3 → 4 → 5 → 6. A inversão foi segura porque os ganhos da Fase 5 são localizados por app; o refactor da Fase 4 reabsorve depois.

## Como executar (regras de sempre)

- Cada fase ganha um **plano detalhado (TDD)** no início da execução: tasks pequenas, 1 commit por task, suíte verde antes do commit, revisão por subagente no fim — como nas Fases 1–2 (planos em `~/.opencode/plans/`).
- Invariantes do projeto: `READ_ONLY=True` intocado · sem PII em logs · UI/mensagens em PT-BR · testes herméticos (sem rede/portal) · `uv run ruff check .` + `uv run python -m pytest -q` verdes por task · **sem push** · `git add` explícito · nunca commitar dados (xlsx/csv/log/zip) nem segredos.
- Gate por app migrado (Fase 4): lote fixo de 2–3 escolas + **comparação semântica** saída antiga × nova (não byte a byte).

---

## Fase 5 — Eficiência da coleta ✅ (5.0–5.8 concluídos)

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
- [x] **5.8 — Protocolo antes/depois.** Planilha fixa de 10 escolas (normais, 2 "não encontrada", 1 paralisada) × 3 execuções com o portal. **Antes: 05m39s (≈33,9 s/escola). Depois: 284,7s / 285,1s / 283,5s → média 284,4s (4m44s), ≈28,4 s/escola (−16%).** Mediana por escola: 29,0s (normais ≈29s; "não encontrada" ≈6,6s; paralisada ≈57s). Saída **equivalente** — idêntica célula a célula (6 abas × 8 escolas; não coletadas com as 2 falhas).
- [ ] **5.9 — (Opcional) Paralelismo piloto.** **P8:** workers por **processo** (cada um com seu `sync_playwright` + context + login + tmp próprio) atrás de flag `WORKERS` — **ou** **P9** operacional: rodar os 4 coletores em paralelo. **Risco alto:** Keycloak single-session (tempestade de re-login) + rate limit → só com piloto de 2 sessões × 10 escolas e log de re-login. Default continua 1.

**Status da Fase 5 (2026-10-18):** **5.0–5.8 concluídos** (5.0–5.7 mergeados no `master`; 5.8 = protocolo antes/depois executado pelo usuário com o portal): **4m44s médios contra 05m39s do baseline (−55s em 10 escolas, −16%), saída idêntica ao antes**. Uma rodada intermediária falhou por instabilidade momentânea do portal (0/10 + falha de login) e foi refeita na sequência, sem ação no app. Durante o protocolo, um bug **pré-existente da UI** de coleta (o monitor não encerrava após concluir: botão de interromper e barra de progresso ficavam presos na tela) foi corrigido nos 4 frontends em `495de94`, com 4 testes de regressão → suíte **129 passed / 33 skipped**, ruff limpo. Bônus de retomada do **5.4 não feito** (dados parciais ficam em `/tmp/educacenso_*_tmp_*` para recuperação manual). **5.9 adiado** (decisão do ciclo; risco Keycloak single-session). Sobras de texto do quadro: o `norm_map` por aba (5.2) e o log quando o portão estourar (5.3) não foram implementados; o "fallback para o wait longo" do sigilo (5.1) foi entregue como `wait_for_timeout(500)`.

**Observações:** `expect_download(60 s)` (geração no portal) é irredutível no cliente — o limite de ganho em Relatórios é menor; a cauda (retry de 30 s do campo de código) deve ser **medida antes** de mexer; `_wait_loader` do gestor tem teto de 15 s (vs 6 s) — não é o ganho médio, é a cauda.

**Foco da revisão:** nenhuma otimização pode alterar dados coletados (comparar amostras); fallback do sigilo obrigatório; paralelismo nunca default.

---

## Fase 3 — Testes golden das regras ✅ (3.1–3.10 concluídos)

**Objetivo:** rede de segurança para as regras de verificação **antes** de qualquer refatoração.
**Estado hoje:** 116 itens coletados; apenas 13 tocam verificação/unificador; **nenhum teste exercita `rules/`**.
**Pronto quando:** cada regra nomeada tem caso positivo + negativo; estimativa: **~198 itens novos** (P0 = 144, P1 = 54), em ~35 funções parametrizadas.

- [x] **3.1 — `tests/rules/conftest.py`.** Fixtures `wb_bytes(sheets)` (openpyxl; nomes ≤ 31 chars) e `df(rows)` + constantes importadas dos próprios módulos (não redigitar cabeçalhos). *Fixtures depois promovidas para `tests/conftest.py` (3.8), para reuso pelos testes de upload/estrutura.*
- [x] **3.2 — `tests/rules/test_unidades.py` (40).** 5 abas válidas; 26 negativos; 5 abas ausentes; bytes inválidos; código/nome por posição (colunas 0/1).
- [x] **3.3 — `tests/rules/test_gestor.py` (34).** 3 abas válidas; 23 negativos; 3 abas ausentes; bytes inválidos; código/nome por posição.
- [x] **3.4 — Turmas (64).** `test_turmas_curricular.py` (30: linha válida, 17 negativos, colunas especiais, dedup, espaços nas pontas) + `test_turmas_escolarizacao.py` (45: sigla↔etapa cobrindo G1–G3/P1–P2 e anos representativos de 1A–9A/1F–9F, MI, cargas M/T/I, merge).
- [x] **3.5 — Aluno (48).** `test_aluno_validacao.py` (36: 12 ramos de idade, 31/03 vs 01/04, `ano_letivo=None`, dedup) + `test_aluno_listagens.py` (12: duplicadas, sem CPF, cor/raça + agregação).
- [x] **3.6 — `tests/rules/test_profissionais.py` (30).** 20 negativos (9 regras); isenção de apoio; agrupamento/dedup; placeholders `-`. *Falso positivo do IFA/tipo-curso ausente pinado como está — candidato à Fase 6.*
- [x] **3.7 — `tests/rules/test_validations.py` (23).** 5 chaves do dispatcher; `expected_columns` (igualdade com as listas canônicas dos adequadores + cobertura das colunas consumidas); helpers de aluno.
- [x] **3.8 — P1: `tests/test_verificacao_upload.py` (42) + `tests/test_checar_estrutura.py` (13).** Contrato de entrada (BOM/`;`/linha-título, splits, colunas derivadas).
- [x] **3.9 — P1: extras do unificador/adequação (115 = 46 + 69).** `_normalize_inep` decimal, `_read_report` multi-abas, categorias desconhecidas, `_safe_filename` (9) + processors de adequação ×3 apps + helpers duplicados (62).
- [x] **3.10 — P1: `tests/test_verificacao_frontend_modes.py` (16).** `_modo_relatorio` (6 configs) + `_build_xlsx` modos `turma`/`aluno`/`profissional`.

**Status da Fase 3 (2026-10-18):** **3.1–3.10 concluídos** na worktree `fase3-testes-golden` (commits `fase 3.1`–`fase 3.10` + ajustes da revisão; merge pendente; **sem push**). Suíte **129 → 565 passed / 33 skipped** = **436 testes novos** (estimativa: ~198 — a diferença são casos de contrato e peculiaridades além das regras nomeadas). Os testes **congelam o comportamento atual** — nenhuma regra foi corrigida. A revisão por subagente foi aplicada: igualdade de `expected_columns` com as listas canônicas dos adequadores (novo `tests/colunas_canonicas.py`), pares sigla↔etapa restantes da escolarização (G2/G3/P2, anos 3–9 e EJA 2F–8F), leitura posicional do código/nome (unidades/gestor), espaços nas pontas do nome da turma e bordas do upload (`_safe_filename` NFC, código/nome placeholder). Peculiaridades pinadas como estão (candidatas à Fase 6): mensagem duplicada de `validate_profissionais` com IFA/tipo de curso ausentes (ids distintos); `validate_unidades` aborta com aba vazia (early-return); `reindex` da adequação casa colunas por rótulo — com menos colunas que o alvo, só as que já tinham o nome final sobrevivem (as demais viram vazias); comparações de texto literais (situação/cor case-sensitive; `"--"` conta como zona preenchida); heurística de linha-título do upload (≤ 3 células) e `_find_column` sem dobra de acentos. Testes herméticos (sem rede/portal), como nas fases anteriores.

**Armadilhas (da auditoria — usar nas fixtures):** idade em **31/03** (`aluno.py:48-52`); `pd.to_datetime(dayfirst=True)` interpreta **ISO errado** — usar `dd/mm/yyyy`; cabeçalhos casam **string exata** (en-dash e typos: `"3 – localizacaoZona"`, `"7b -Término (previsão)"`); abas ≤ 31 chars; **aba vazia causa early-return** em `validate_unidades` (fixtures com ≥1 linha em todas as 5 abas); valores viram `str()` — gravar texto, não datas do Excel; usar `dtype=str` (CPF float → `"…0"` é descartado); `validate_profissionais` tem **falso positivo** com coluna ausente (`:42-46` — se virar comportamento testado, decidir se corrige na fase).

**Foco da revisão:** fidelidade das fixtures ao formato real do Educacenso (typos inclusos); testes não devem "consertar" as regras — só congelar o comportamento atual.

---

## Fase 4 — Refatoração `apps/common` ✅ (4.1–4.8 concluídos; sem mudança de comportamento)

**Objetivo:** eliminar **~2.400–2.700 linhas duplicadas**; módulos `apps/common/{auth, school_list, session, browser, export, ui}.py`; **piloto: Relatórios** (menor atrito — similaridade 0,78/0,91 com Recibos).
**Pronto quando:** 4 coletores + verificação consumindo os comuns; hack de `sys.path` removido; suíte verde; saídas equivalentes por app.

- [x] **4.1 — `apps/common/auth.py`.** `BASE_URL`, `READ_ONLY`, `assert_read_only()`; os 4 `auth.py` viram re-export.
- [x] **4.2 — `apps/common/school_list.py`.** `_find_column` + `read_school_list` (verificação passa alias `"unidade escolar"` e não exige nome).
- [x] **4.3 — `apps/common/session.py` + `browser.py`** (extraídos do Relatórios, quase 1:1): `login_and_read`, `accept_sigilo_if_present`, `select_school(after_select=…)`, `marcar_nao_processadas`, `LoginFalhou`/`SessaoExpirada`; `safe_cleanup`, `wait_loader`, `session_expirada`, `raise_if_expired`. **Manter wrappers** com os nomes antigos no módulo do app (monkeypatch dos testes).
- [x] **4.4 — `apps/common/export.py` + `run_coleta` genérico.** Temporários, "não coletadas", ZIP/XLSX; loop com `scrape_one` + mapa exceção→motivo + `accept_downloads` (wrapper preserva assinatura pública).
- [x] **4.5 — `apps/common/ui.py`.** `SUBMIT_CSS`, chromium, `init_state`/`monitor`/`finalize`/worker/start parametrizados pelo dict de config; `render_report_frontend(config, logo)` intacto.
- [x] **4.6 — Migrar Recibos** (valida parametrização CSV↔PDF nos mesmos módulos).
- [x] **4.7 — Migrar Gestor + Cadastros.** Remove o hack de `sys.path` (`app.py:12-18`, `tests/conftest.py:12-14`) e imports `src.*` → relativos.
- [x] **4.8 — Verificação** consome `school_list`/`export` (sem fundir `_load_structure` linha-1 com `load_model` linha-2).

**Status da Fase 4 (2026-10-19):** **4.1–4.8 concluídos** na linha `fase4-t8-t9`. T0–T7 (`d9ad42f`…`e965575`) mergeados antecipadamente em `--no-ff` → `c4fc628` (a pedido do usuário, antes da T8/T9), com **gates ao vivo 1–3 aprovados pelo usuário** (lote `escolas_teste03.xlsx`; saídas iguais entre master e linha nova — relatórios, recibos, cadastros célula a célula e gestor). T8 (`94bb39b`) migra a verificação para `apps/common/school_list.py` (`require_nome=False`, alias `"unidade escolar"`), **sem tocar** em `_load_structure`/`checar_estrutura`; T9 fecha com **revisão por subagente** do diff `82d7300..94bb39b` (foco: monkeypatches, strings exatas, paridade do loop, import graph, Chromium, divergências) e correções. Suíte **565 → 652 passed / 33 skipped**; `ruff` limpo; **sem push**. A revisão pegou **1 achado Critical real**: o `run_coleta` genérico havia perdido o **mapa exceção→motivo** de Relatórios/Recibos (`PreenchimentoNaoIniciado`/`RelatorioInexistente`/`ReciboIndisponivel` caíam em `"Erro: "` e na planilha de não coletadas); corrigido em `09dc812` com `TextosColeta.mapear_excecao` + 3 testes de regressão no nível de `run_*` (RED→GREEN). **Gate ao vivo 4 aprovado pelo usuário (2026-10-19)** (verificação real na linha nova) e **merge `--no-ff` → `87e646d`** (suíte 652/33 e ruff verdes no pós-merge; push para o `origin/master` em 2026-10-19). Demais achados da revisão: minor (deferidos; ver plano da fase).

**Divergências convergidas (declaradas):** (a) rel/rec ganham o log `"[codigo] Falha no re-login: …"` no handler de `SessaoExpirada`; (b) rel/rec: falha de `select` no retry pós-`SessaoExpirada` passa a motivo `"Escola não encontrada"` (era `RelatorioInexistente` → `"Erro (após re-login): "`); (c) ordem `scrape → stop_check → None` unificada na do CAD; (d) rel passa a ter a guarda de Chromium (já padrão nos outros 3); (e) `_assert_read_only` local de rel/rec converge para a mensagem canônica (caminho inalcançável com `READ_ONLY=True`); (f) monitor do CAD/GES passou a usar a renderização colorida/escapada do comum (era `st.write`); (g) `init_state` pré-cria a chave genérica `{p}zip` (a chave real do app é criada no start/finalize; contrato de 8 chaves pinado por teste). Nenhuma altera dados coletados, motivos de não coletadas, nomes de arquivo ou chaves de estado dos apps.

**Riscos mapeados (resumo dos 18):** chaves `session_state` prefixadas (`rt_`/`ra_`) vs literais (`ws_`/`cg_`); **mensagens assertadas em testes** (`"Falha no login"`, `"Escola não encontrada"`, `"Coleta interrompida (não processada)"`, `"Erro (re-login):"`…); timeouts divergentes (gestor `_wait_loader` 15 s; `_open_school_ficha` goto 30 s vs 15 s); sigilo do gestor restrito a `mat-dialog-container`; `_ensure_chromium` ausente no Relatórios; **3 formatos de nome de arquivo** (`cadastro_escola_educacenso_*`, `vinculo_gestor_educacenso_*`, `{prefix}_educacenso_*` e recibos **sem** "educacenso"); prefixos de tmp exigidos por teste; logger por app (não fixar 1); re-login com formatos de motivo diferentes (`{exc}` vs `{str(exc) or type(exc).__name__}`).

**Foco da revisão:** zero mudança de comportamento observável (mensagens/chaves/nomes de arquivo/nº de abas); gate de comparação semântica por app migrado; monkeypatches sobrevivem.

---

## Fase 6 — Régua fina ✅ (6.1–6.7 concluídos)

- [x] **6.1 — "Pisca" na troca de apps.** Causa provável: **replay da animação CSS** `fadeIn 0.7s` do `.title-container` (`app.py:347`) quando o banner é recriado na troca; secundária: banners da página anterior durante o rerun; e um caso real: `st.success` imediatamente antes de `st.rerun()` (`verificacao/frontend.py:735-739`). Opções: (a) remover a animação; (b) remover o `st.rerun()` da nav (`app.py:653`); (c) remover o `st.success` redundante. (`st.fragment` **não** se aplica à troca de páginas.) Testar cada opção isolada.
- [x] **6.2 — `checar_estrutura`/`_REFERENCIA_BYTES`: DECISÃO EM ABERTO.** Hoje silenciosamente inerte (`verificacao/frontend.py:22-40`, `:741-748`; pasta `arquivos de teste/` não existe no git). Opções: **(a)** versionar referências sintéticas só-cabeçalho em `apps/verificacao_inconsistencias/docs/` (+ teste "referência carrega"; ponto de manutenção quando o layout mudar) **ou (b)** remover o recurso (+ `checar_estrutura.py`). Mínimo: logar "checagem desativada" enquanto decidir.
- [x] **6.3 — `_status_color`: ramo morto.** Remover `or estado.startswith("Falha no login")` em `coleta_relatorios/src/frontend.py:267` e `coleta_recibos_fechamento/src/frontend.py:299` (o login falho nunca passa por `on_progress`).
- [x] **6.4 — `.gitignore`.** Adicionar `*.xlsx`/`*.xls` + negações `!apps/*/docs/modelo*.xlsx` (os 2 modelos rastreados não são afetados; corrige claims falsos no AGENTS.md e no PDF).
- [x] **6.5 — `AGENTS.md` (reescrever seção de estado).** Corrigir: "5 apps" → 10; caminhos dos modelos; `sheets.py` **não existe** (remover menção); `.opencode/agents/*` **não existem**; gitignore de xlsx; refs de linha defasadas (`app.py:347`/`646-653`/`673-683`); "Estado atual" de 2026-08-04 → atual; contagem de testes.
- [x] **6.6 — PDF de documentação (`apps/inicio/documentacao.py`).** "6 testes" → suíte offline completa (83+33); incluir comandos da suíte offline (seção 3.3); tabela Visão Geral omite o grupo **Adequação** (3 linhas + subseção); caminhos dos modelos; alvo dos testes ao vivo sem padrão — `SECURITY_TARGET` obrigatório (alinhar com `tests/security/conftest.py`); claim de gitignore; menção a Google Sheets.
- [x] **6.7 — Política de cache PII (`st.cache_data` ×5, todos globais sem TTL).** Mínimo: `ttl` curto (300–900 s) nos 5; alvo LGPD: memoizar em `st.session_state` os 4 com PII e manter cache só do agregado. *`verificacao/frontend.py:72,116,195,224,253`.*

**Foco da revisão:** cada item é independente; nada de mudança de comportamento fora do descrito; decisões (6.2/6.7) registradas no commit.

**Status da Fase 6 (2026-10-19; encerrada em 2026-10-20):** **6.1–6.7 concluídos** na worktree `fase6-regua-fina` (commits `fase 6.1`–`fase 6.7`: `8b94f19`, `7a49808`, `15041d3`, `2cfd325`, `e5467b4`, `0ac83f1`, `4a348e9`). **6.1:** animação `fadeIn` do banner removida (fim da "piscada"; o `st.success` antes do `st.rerun()` ficou — é feedback funcional). **6.2:** referências sintéticas só-cabeçalho versionadas em `apps/verificacao_inconsistencias/docs/` (geradas pela mesma função `build_xlsx` dos coletores) + `tests/test_verificacao_referencias.py`; a checagem de estrutura deixou de ser silenciosamente inerte (o ponto de manutenção futura é regenerar as referências junto com os modelos). **6.3:** ramo morto removido onde ele realmente vive hoje (`apps/common/ui.py`, pós-refactor da Fase 4 — as linhas citadas na spec ficaram defasadas) + pino do teste ajustado. **6.4:** `*.xlsx`/`*.xls` ignorados por padrão, com negações para os modelos e as referências. **6.5/6.6:** `AGENTS.md` e PDF corrigidos (10 apps, caminhos dos modelos, grupo Adequação na tabela do PDF, seções do PDF renumeradas, suítes/comandos, `SECURITY_TARGET` obrigatório alinhado a `tests/security/conftest.py`, fim das menções a Google Sheets). **6.7:** memo por sessão nos 4 relatórios com PII — com chave por recorte de download (refinamento sobre a chave única planejada: cada tela tem várias listagens e a chave única nunca acertaria o memo, permitindo regeração a cada clique) — sem regenerar bytes no clique de download — e `st.cache_data` com `ttl=300` só no agregado cor/raça. Suíte **652 → 660 passed / 33 skipped** (+8 testes: 3 referências, 1 PDF, 4 memo); `ruff` limpo. **Revisão por subagente aplicada** (achados corrigidos no ramo — claims do PDF, sumário e AGENTS.md); **gate do usuário aprovado (2026-10-20) e merge `--no-ff` → `9f880ac`** (suíte 666/33 e `ruff` verdes no pós-merge; o hotfix da coleta do gestor, `151e189`, foi integrado antes); **sem push.**

---

## Extras

### Operação (fora do código)

- [ ] **E3 — Apagar `credenciais.json` da raiz** ⚠️ **MANTER** por enquanto. Credenciais podem ser necessárias para testes futuros de coleta. Apagar apenas após validação definitiva do ambiente de produção.
- [x] **E5 — Push dos commits locais** para `origin/master` (2026-10-18; CI passa a rodar no GitHub; revalidado em 2026-10-20 com `8df55fb`).
- [x] **E6 — Execução local com uv (redefinida em 2026-10-20).** Sem Docker/Caddy e sem TLS por padrão, sem autenticação de aplicação: `uv sync` + `uv run streamlit run app.py --server.port <porta>` no servidor local; porta escolhida a cada janela; Chromium/deps no host; logs nativos; runbook `docs/deploy.md`. **Validação local (2026-10-20):** suíte **655 passed / 19 skipped** + ruff; HUB em `:8599` com health `ok`, Tela Inicial sem login, navegação até a coleta e PDF de 46 KB baixado; auditoria HTTP **19/19**. O deploy real é manual, nas janelas de uso do operador (5–15×/ano); a stack Docker/Caddy do ensaio foi removida.
- **LGPD:** responsabilidade pessoal do usuário (decisão de 2026-10-18).

---

## Concluído (histórico)

- [x] **Fase 1 — Hotfixes P0/P1** (8 itens: temporários isolados, interrupção na troca de página, escolas "não coletadas", sessão expirada no download, escape HTML, neutralização de fórmulas, reportlab/devcontainer) — mesclada.
- [x] **Fase 2 — Intranet + autenticação + CI/logging** (Docker+compose+Caddy/TLS, `auth_gate` oidc/senha/aberto, CI pytest+ruff, logging rotativo sem PII, runbook `docs/deploy.md`) — mesclada (`c37aa4f`). **Substituída pela operação local em 2026-10-20:** Docker/Caddy/auth removidos; ver E6.
- [x] **Revisão completa do plano** com 4 auditorias (2026-10-18) — este documento.

## Fora de escopo (decidido)

Reescrita FastAPI/React · `sync→async` do Playwright · APIs internas do portal · Polars/duckdb · WeasyPrint/Typst · SPA · **Histórico/BI** (próxima onda, não selecionado) · **Hospedagem externa** (cloudflared/Oracle VM) — descartada em 2026-10-18: implantação somente na rede interna da SEDUCT, administrada pela equipe interna.

## Decisões em aberto

1. **6.2 — RESOLVIDA (2026-10-19):** referências sintéticas só-cabeçalho versionadas em `apps/verificacao_inconsistencias/docs/` (a checagem de estrutura deixou de ser inerte).
2. **6.7 — RESOLVIDA (2026-10-19):** memo por sessão nos 4 relatórios com PII (alvo LGPD); `ttl=300` só no agregado cor/raça.
3. **Fase 4 — RESOLVIDA (2026-10-19):** preservar wrappers/monkeypatch antigos + adaptar imports dos testes **mecanicamente** (9 arquivos; nenhum corpo de teste mudou). O contrato segue "sem mudança de comportamento observável".
4. **Ordem das fases** — sugerida 5 → 3 → 4 → 6; confirmar na largada de cada uma.
5. **Operação local — RESOLVIDA (2026-10-20):** sem Docker/Caddy/TLS e sem autenticação própria; execução manual com `uv` + Streamlit, porta escolhida na hora e acesso restrito à rede (firewall/VPN). A senha do Educacenso protege as coletas; o reinício após queda fica no script externo do operador.
