# Coleta Automática — documento de design

- **Data:** 20/10/2026
- **Branch:** `automacao-coleta` (worktree `/home/rodrigo/.local/share/opencode/worktree/1803e6/automacao-coleta`)
- **Status:** aguardando aprovação do usuário (design fechado; §7 resolvido)

---

## 1. Intenção e o porquê

Hoje o operador do HUB precisa rodar as coletas do Educacenso **uma a uma**: abrir a
tela de Cadastrais, colar CPF e senha, subir a lista de escolas, esperar, baixar o
arquivo; depois repetir o mesmo na tela do Gestor, depois nas três telas de
Relatórios e por fim na de Recibos. São seis rodadas manuais, com a mesma credencial
digitada seis vezes e seis planilhas de escolas para subir.

A aplicação **Coleta Automática** existe para executar essas seis etapas em uma
única rodada, em segundo plano, com a credencial e a lista de escolas informadas
uma vez só. O resultado é o mesmo material de antes — cada etapa continua produzindo
exatamente o artefato que produz hoje —, mas reunido e com o tempo de cada etapa
visível.

O ganho que importa não é o tempo total, é **a previsibilidade**: o operador vê, em
uma tela, o que rodou, quanto tempo cada etapa levou, o que deu erro e onde baixar
cada coisa. Hoje, se a coleta de recibos falha na 80ª escola, ninguém descobre sem
repetir a rodada na mão.

## 2. Objetivos, não-objetivos e anti-objetivos

### Objetivos

1. Uma tela nova no grupo **Coleta do Educacenso**, chamada **"Coleta Automática"**,
   com CPF, senha e lista de escolas informados **uma vez**.
2. Rodar as etapas selecionadas **em sequência, em background**, sem navegar pelas
   telas dos outros coletores.
3. Gerar **um ZIP único** com os artefatos de todas as etapas executadas.
4. Mostrar o **relógio** (já existente no HUB) e, acrescentado a ele, o **tempo
   particionado por aplicação**.
5. Permitir **selecionar quais aplicações** entram na rodada (checkbox por linha).
6. Manter o **mesmo esqueleto visual** das demais telas: cabeçalho padrão, botões
   azuis, card de Orientações de uso, tipografia e cores do tema.

### Não-objetivos (fora desta entrega)

- Não alterar o comportamento de nenhum dos seis coletores existentes.
- Não paralelizar etapas (o plano do projeto já descartou o paralelismo: risco de
  tempestade de re-login e de *rate limit* do Keycloak).
- Não criar um histórico/banco de rodadas passadas.
- Não extrair a lógica de coleta para fora dos coletores existentes.
- Não mexer no motor compartilhado `apps/common/coleta.py` nem nos `auth.py`.

### Anti-objetivos (o que seria uma falha, mesmo funcionando)

- **Quebrar os coletores atuais.** A refatoração da Fase 4 congelou o contrato
  "sem mudança de comportamento observável" e existe uma bateria de testes *golden*
  sobre o motor de coleta. A aplicação nova **consome** os coletores; não os altera.
- **Duplicar credencial em disco.** A senha do Educacenso fica em memória, na sessão
  do Streamlit, exatamente como nos coletores de hoje — nunca é gravada em arquivo.
- **Deixar a rodada rodando sem controle.** O operador precisa poder interromper a
  rodada inteira, e a interrupção precisa ser segura (a escola em andamento é
  descartada e marcada como não coletada, como já acontece hoje).

## 3. Restrições

| Restrição | Origem |
|---|---|
| Python 3.14, `uv`, Streamlit 1.58 | `pyproject.toml` |
| `playwright.sync_api` (nunca async), `READ_ONLY = True` | `AGENTS.md`, cláusula pétrea de modo leitura |
| Login só via Keycloak em `acesso.inep.gov.br`, com CPF e senha | `AGENTS.md` |
| Coletas em série; sem paralelismo | decisão registrada em `docs/historico/plano_de_melhoria.md` (5.9) |
| Cabeçalho, colunas, botões azuis, card de Orientações e relógio: usar os componentes de `apps/common/` | padronização do HUB (20/10/2026) |
| Nada de escrita no Educacenso | modo leitura |

## 4. Decisões do usuário (como ele decidiu)

Estas foram tomadas na conversa e **não** são sugestões do implementador:

1. **Escopo da rodada:** as 6 etapas — Cadastrais, Gestor, Relatórios de Turmas,
   Relatórios de Alunos, Relatórios de Profissionais e Recibos de Fechamento.
2. **Falha em uma etapa:** **interrompe a rodada** (não segue para a próxima).
3. **Conteúdo do ZIP único:** os artefatos de cada etapa **como são**, cada um em
   uma pasta nomeada (sem descompactar os ZIPs intermediários).
4. **Credenciais:** digitadas uma vez, reaproveitadas por todas as etapas.
5. **Execução:** em background, chamando o código dos coletores — **sem** navegar
   visualmente pelas telas dos outros coletores.
6. **Download por etapa:** botão na linha da tabela quando a etapa está "Concluída",
   disponível **durante** a rodada.
7. **Pacote completo:** só aparece quando a rodada termina **sem interrupção**.
8. **Seleção de aplicações:** checkbox à esquerda de cada linha, antes de executar.
9. **Layout da tela inicial** (v5 do rascunho): Orientações de uso em card de
   largura total no topo; logo abaixo, o card de acesso (CPF | Senha | Lista) com
   os campos lado a lado; abaixo dele, o card "Aplicações a coletar" com as 6
   opções em duas colunas e o botão **Executar** no fim delas.
10. **Nome do item de menu:** "Coleta Automática".
11. **Etapa que roda sem erro mas não coleta nenhuma escola:** a rodada **para**,
    mostra a informação de que a etapa não coletou nenhuma escola e **pergunta ao
    usuário se deseja continuar**. Respondendo "continuar", a rodada pula para a
    próxima etapa; respondendo "encerrar", a rodada termina.

Rascunhos visuais aprovados (arquivos `.superpowers/brainstorm/…/content/`):
`tela-coleta-automatica-v3.html` (download por etapa + pacote completo),
`tela-coleta-automatica-v6.html` (layout final da tela inicial).

### Decisões do implementador (ajustáveis pelo usuário)

- **Sessão do Educacenso:** cada etapa faz o **próprio login**, como acontece hoje
  quando o operador roda as telas uma a uma. A alternativa (uma sessão compartilhada
  entre as 6 etapas) exigiria mexer no motor compartilhado `run_coleta` e nos
  `auth.py` de todos os coletores — mudança arriscada e fora do escopo.
- **Todas as 6 aplicações vêm marcadas** por padrão (o caso comum é "roda tudo").
- **Uma sessão expirada no meio da etapa** — que o coletor sabe recuperar com
  re-login — **não** interrompe a rodada: a etapa termina e as escolas afetadas vão
  para a planilha de "não coletadas". Ver §7 para o que interrompe.
- **No estado interrompido** não há ZIP parcial: as etapas concluídas continuam
  baixáveis uma a uma.
- **Interrupção entre etapas:** o `Event` de parada é conferido **antes** de cada
  etapa. A etapa cortada fica "Interrompida" e as seguintes "Não executada".
  (Sem isso, "Interromper rodada" só pararia a etapa corrente e a rodada abriria o
  navegador para as 5 restantes.)
- **Artefatos ficam em disco**, na pasta temporária da rodada, e não em bytes na
  sessão. O botão de download usa `st.download_button(data=<callable>)`: o Streamlit
  1.58 só materializa o arquivo **no clique**, o que evita re-hash de dezenas de MB
  a cada rerun do monitor (que acontece a cada 0,5 s).
- **Tabela com botões:** cada linha é uma fileira de `st.columns`
  (`Aplicação | Situação | Tempo | Resultado | Download`), com o cabeçalho em
  HTML acima. `st.table`/`st.dataframe` não hospedam widgets.
- **Linha viva ("Escola X coletando…"):** o runner publica o **objeto** `shared`
  da etapa em andamento (não uma cópia) no estado da rodada; o frontend lê
  `current`/`last` dele sob o lock, como `monitor_base` já faz hoje.
- **Plano de pendências por etapa:** só é gerado para etapa que **concluiu com
  falhas parciais**; etapa que falhou não ganha planilha (a lista seria a própria
  mensagem de falha em forma de planilha).
- **Na rodada interrompida**, as etapas concluídas com falhas continuam acessíveis:
  a coluna Download ganha um segundo botão ("Pendências") quando há planilha.
- **Nova rodada:** os estados de resultado trazem um botão "Nova rodada" que volta
  ao formulário **mantendo as credenciais e a seleção**. Iniciar uma nova rodada
  substitui os resultados da anterior — o operador deve baixar antes de rodar de
  novo.
- **Posição no menu:** "Coleta Automática" é o **primeiro** item do grupo "Coleta do
  Educacenso". O teste de navegação `tests/test_hub_navegacao.py` acessa os botões
  **por índice** e precisa ser adapted para buscar **por rótulo** (o próprio
  documento já pede um teste de menu novo nesse arquivo).

## 5. Desenho

### 5.1 Onde a aplicação nasce

Novo pacote `apps/coleta_automatica/`, seguindo o desenho dos outros apps:

```
apps/coleta_automatica/
  src/frontend.py     # tela (formulário, monitor, resultado)
  src/runner.py       # orquestração da rodada: sequência, tempos, artefatos
  src/etapas.py       # o registro das 6 etapas (dados + callables)
  src/__init__.py
```

Item de menu em `app.py`, no grupo `"Coleta do Educacenso"` (primeiro da lista).
Roteamento no mesmo arquivo, chamando
`render_coleta_automatica_frontend(logo_base64)`.

O `AGENTS.md` passa a listar o app (11 apps) e o plano de melhoria ganha uma seção
"Fase 7 — Coleta Automática".

### 5.2 As 6 etapas

Cada etapa é uma entrada de um registro (`apps/coleta_automatica/src/etapas.py`) com
os **mesmos** objetos que as telas de hoje usam — nada é reimplementado:

| # | Etapa | App de origem | `config` | Artefato |
|---|-------|----------------|---------|----------|
| 1 | Cadastros das escolas | `coleta_cadastros_escolas` | `CONFIG` (prefixo `ws_`, `zip_prefix="cadastro_escola"`, `construtor_arquivo="build_xlsx"`) | `cadastro_escola_educacenso_DD-MM-AAAA.xlsx` |
| 2 | Cadastro do gestor | `coleta_gestor` | `CONFIG` (prefixo `cg_`, `zip_prefix="vinculo_gestor"`, `build_xlsx`) | `vinculo_gestor_educacenso_DD-MM-AAAA.xlsx` |
| 3 | Relatórios de Turmas | `coleta_relatorios` | `REPORTS["turmas"]` (prefixo `rt_`, `relatorio_turmas`) | `relatorio_turmas_educacenso_DD-MM-AAAA.zip` |
| 4 | Relatórios de Alunos | `coleta_relatorios` | `REPORTS["alunos"]` (prefixo `ra_`, `relatorio_alunos`) | `relatorio_alunos_educacenso_DD-MM-AAAA.zip` |
| 5 | Relatórios de Profissionais | `coleta_relatorios` | `REPORTS["profissionais"]` (prefixo `rp_`, `relatorio_profissionais`) | `relatorio_profissionais_educacenso_DD-MM-AAAA.zip` |
| 6 | Recibos de Fechamento | `coleta_recibos_fechamento` | `CONFIG` (prefixo `rf_`, `recibos_fechamento`) | `recibos_fechamento_DD-MM-AAAA.zip` |

O registro guarda, por etapa: a chave, o rótulo exibido, o `config`, o `zipper`
(módulo `exporter`/`zipper` do app), o `scrape_worker` (a assinatura
`config`-primeiro que o `FrontendCtx` já usa) e o `textos`.

### 5.3 A rodada (thread)

`apps/coleta_automatica/src/runner.py` implementa a sequência **fora** do Streamlit
(mesmo princípio de `apps/common/ui.py::worker_base`: a thread não toca em `st.*`).

Para cada etapa selecionada, em ordem:

1. Se o `Event` de parada estiver marcado, encerrar a rodada (as etapas restantes
   ficam "Não executada").
2. `t0 = time.monotonic()`; a pasta temporária da etapa é criada dentro da pasta
   temporária **da rodada**.
3. `shared = {"current": None, "last": None, "count": 0, "total": len(escolas),
   "done": False, "error": None, "interrupted": False, "failures": []}`; o objeto é
   publicado no estado da rodada (para a linha viva) e entregue ao worker.
4. `etapa.scrape_worker(config, login, senha, escolas, stop_event, lock, shared, pasta)`
   — o worker **do próprio app**, que abre o navegador, faz o login e grava os
   arquivos da etapa na pasta temporária. É o mesmo código que roda hoje na tela
   daquela etapa.
5. Classificação da etapa:
   - **erro do worker** (`shared["error"]`) ⇒ a etapa é marcada "Falhou", com o
     motivo, e a **rodada para**;
   - **etapa concluída sem coletar nenhuma escola** ⇒ a etapa é marcada
     "Concluída (sem dados)", a **rodada pausa** e pergunta ao usuário se deseja
     continuar (§5.3, passo 5a);
   - **etapa concluída com coleta** ⇒ o artefato é montado (passo 6).
6. O artefato é montado com o mesmo par usado em `finalize_base`:
   `getattr(etapa.zipper, config.get("construtor_arquivo", "build_zip"))(tmp_dir=pasta)`
   e nomeado com `etapa.zipper.output_filename(config["zip_prefix"])`. O arquivo é
   gravado em disco e **não** copiado para a sessão.
7. A planilha de "escolas não coletadas" (`apps/common/export.py::build_pending_xlsx`,
   nomeada com `pending_filename`) é gerada quando a etapa **concluiu** e houve
   falhas, e vai junto do artefato da etapa.
8. O estado da etapa (situação, tempo em segundos, caminho do artefato, caminho da
   planilha, motivo da falha) é publicado no dicionário da rodada, sob o lock.

**5a — Pausa por etapa sem coleta.** Quando a etapa termina sem coletar nenhuma
escola, o runner publica `ca_aguardando = <índice da etapa>` e **fica esperando**
(o `Event` `ca_continuar`), enquanto o monitor continua desenhando a tela e o
relógio segue correndo. A tela mostra a informação *"A etapa X não coletou nenhuma
escola"* com dois botões: **Continuar** (libera `ca_continuar` e a rodada segue
para a próxima etapa) e **Encerrar a rodada** (marca o `Event` de parada e a
rodada termina). A espera é feita em laço curto (0,5 s) conferindo o `Event` de
parada, para que o "Interromper rodada" continue valendo durante a pausa.

Interrupção: o botão "⛔ Interromper rodada" apenas marca o `threading.Event`; o
`stop_check` já existente em `run_coleta` faz o coletor encerrar com segurança (a
escola em andamento é descartada e as restantes marcadas como não coletadas). A
thread termina, a etapa em andamento é marcada como "Interrompida" e a rodada para
antes da etapa seguinte.

### 5.4 Estado da sessão

Prefixo novo: `ca_` (Coleta Automática). Chaves:

| chave | conteúdo |
|-------|----------|
| `ca_running` | rodada em andamento |
| `ca_stop` | `threading.Event` da interrupção |
| `ca_lock` | `threading.Lock` do dicionário compartilhado |
| `ca_shared` | dicionário da rodada (etapa atual, contadores, resultados) |
| `ca_thread` | thread da rodada |
| `ca_finalized` | rodada encerrada |
| `ca_inicio` / `ca_fim` | `datetime` de início e de término |
| `ca_etapas` | resultados por etapa (situação, tempo, caminhos, motivo) |
| `ca_zip` | `(caminho, nome)` do pacote completo (só quando não houve interrupção) |
| `ca_pasta` | pasta temporária da rodada (artefatos em disco) |
| `ca_aguardando` | índice da etapa que paused a rodada aguardando confirmação (ou `None`) |
| `ca_continuar` | `threading.Event` que o usuário dispara em "Continuar" |

O `Event` `ca_stop` é desligado automaticamente ao trocar de página: o
`hub_sessao.liberar_execucoes` marca qualquer `threading.Event` encontrado na
sessão.

### 5.5 A tela

Reaproveita o que já existe:

- `apps/common/banner.py::banner_titulo` — cabeçalho padrão.
- `apps/common/orientacoes.py::card_orientacoes` — card de Orientações de uso.
- `apps/common/ui.py::RELOGIO_CSS`, `_duracao`, `_horario`, `_relogio_andamento_html`,
  `_relogio_resumo_html` — o relógio (criado em 20/10/2026) e o resumo de tempos.
- `apps/common/school_list.py::read_school_list` — leitura da lista de escolas
  (mesmo formato e tolerâncias das coletas atuais).

**Estado 0 — formulário** (rascunho v5):

1. Cabeçalho padrão ("Coleta Automática").
2. Card de **Orientações de uso** em largura total, com os 5 passos (credenciais,
   lista, marcar as aplicações, Executar, downloads).
3. Card **Acesso ao Educacenso** em largura total: `Login (CPF)`, `Senha` e
   `Lista de escolas` lado a lado (3 colunas).
4. Card **Aplicações a coletar** em largura total: as 6 opções com checkbox à
   esquerda, em 2 colunas (1‑3 / 4‑6), o contador "N de 6 aplicações selecionadas"
   e, no fim das opções, o botão **Executar**.

A tela **não** usa `st.form`: o botão "Executar" precisa ficar no fim das opções
selecionáveis (que fica fora do formulário) e o contador precisa atualizar a cada
clique. Os valores dos widgets são lidos do estado da sessão no clique do botão —
o mesmo comportamento observável de hoje.

**Estado 1 — em andamento**: o relógio digital no topo (total em andamento +
horário de início), a tabela **Tempo por aplicação** e o botão "⛔ Interromper
rodada". A tabela lista **somente as etapas selecionadas**, com as colunas:
Aplicação | Situação | Tempo | Resultado | Download. A coluna Download traz o
botão "Baixar" assim que a etapa conclui; enquanto isso, "—". A linha da etapa em
andamento mostra a escola que está sendo coletada.

**Estado 1b — pausada aguardando confirmação**: a etapa terminou sem coletar
nenhuma escola. A tela mantém o relógio e a tabela, e acrescenta a informação
*"A etapa X não coletou nenhuma escola"* com os botões **Continuar** (segue para a
próxima etapa) e **Encerrar a rodada**.

**Estado 2 — concluída sem interrupção**: o resumo (horário inicial, horário de
término, tempo de execução total), a tabela completa com o tempo de cada etapa, o
cartão **Pacote completo** com o botão "Baixar ZIP com todas as coletas" e o botão
"Nova rodada".

**Estado 3 — interrompida**: o resumo, a tabela com a etapa que falhou em vermelho
(motivo) e as seguintes como "Não executada", e no lugar do pacote completo o
aviso "Rodada interrompida na etapa N — o pacote completo não é gerado", com a
nota de que as etapas concluídas continuam baixáveis arquivo por arquivo.

### 5.6 O pacote completo

Um ZIP (`coleta_completa_DD-MM-AAAA.zip`), montado no fim da rodada a partir dos
arquivos em disco, com uma pasta por etapa:

```
cadastros_escolas/cadastro_escola_educacenso_20-10-2026.xlsx
cadastros_escolas/cadastro_escola_escolas_nao_coletadas_20-10-2026.xlsx
gestor/vinculo_gestor_educacenso_20-10-2026.xlsx
gestor/vinculo_gestor_escolas_nao_coletadas_20-10-2026.xlsx
relatorios_turmas/relatorio_turmas_educacenso_20-10-2026.zip
relatorios_turmas/relatorio_turmas_escolas_nao_coletadas_20-10-2026.xlsx
…
```

A planilha de pendências só entra quando a etapa tiver falhas. O pacote é gerado
apenas quando **nenhuma** etapa foi interrompida ou falhou.

### 5.7 Receitas e limites conhecidos

- `read_school_list` (em `apps/common/school_list.py`) é a mesma função usada
  pelas telas de coleta; a lista informada tem as colunas `código do inep` e
  `nome da unidade` (tolerante a maiúsculas/minúsculas).
- Os coletores gravam os arquivos da etapa em pasta temporária por execução e a
  consolidação final acontece depois; a etapa gera **um** artefato, não vários.
- `worker_base` engole exceções e as publica em `shared["error"]`; é esse sinal
  que a rodada usa para classificar a etapa como falha.
- `build_xlsx`/`build_zip` produzem um arquivo válido mesmo com zero escolas
  coletadas — por isso "zero escolas" **não** é, sozinho, sinal de falha (§7).
- Os seis coletores abrem o navegador e fazem login sozinhos. A rodada **não**
  compartilha sessão entre etapas (ver decisão do implementador).
- `st.download_button` aceita `data=<callable>` no Streamlit 1.58: o arquivo só é
  materializado no clique.

## 6. O que está entregue ao construtor

Implementar:

1. `apps/coleta_automatica/src/etapas.py` — o registro das 6 etapas (§5.2).
2. `apps/coleta_automatica/src/runner.py` — a sequência em thread (§5.3).
3. `apps/coleta_automatica/src/frontend.py` — a tela nos 4 estados (§5.5) e o
   pacote completo (§5.6).
4. `app.py` — item de menu e roteamento.
5. Testes:
   - `tests/test_coleta_automatica.py` — registro das etapas (as 6, com os
     `config` certos), sequência da rodada (com um worker falso por etapa),
     classificação de falha (worker com `error` ⇒ rodada para), **pausa por etapa
     sem coleta** (a rodada espera a confirmação e só segue após "Continuar"),
     interrupção antes de uma etapa, construção do pacote completo (com a árvore de
     pastas) e a **ausência** do pacote quando a rodada é interrompida.
   - `tests/test_hub_navegacao.py` — passar a localizar os botões do menu **por
     rótulo** (hoje são por índice) e acrescentar o teste da nova aplicação.
   - Manter a suíte existente verde (655 testes hoje) — nada dos coletores muda.
6. Documentação: `AGENTS.md` (11 apps, o item de menu, a convenção do relógio) e
   `docs/historico/plano_de_melhoria.md` (seção da Fase 7).
7. O PDF de documentação (`apps/inicio/documentacao.py`): incluir a aplicação na
   tabela da Visão Geral e um parágrafo na seção de Coleta, se couber no padrão
   atual do documento.

Não decidir aqui: os nomes das pastas internas do pacote (o construtor pode
escolher nomes legíveis) e o texto exato das mensagens de erro.

## 7. Pergunta em aberto (para o usuário)

**Resolvida em 20/10/2026 — quando uma etapa roda sem erro mas não coleta nenhuma
escola, a rodada para e pergunta.**

O coletor considera "sucesso" uma etapa que rodou e gravou arquivos; `build_xlsx`
e `build_zip` produzem um arquivo válido mesmo com zero escolas. Logo, "zero
escolas coletadas" é ambíguo: pode ser **login recusado** (a etapa está quebrada) ou
**não havia o que coletar** (ex.: nenhuma escola tem recibo de fechamento).

**Decisão do usuário:** a rodada **para**, mostra a informação de que a etapa não
coletou nenhuma escola e **pergunta se deseja continuar**. Respondendo "continuar",
a rodada pula para a próxima etapa; respondendo "encerrar", a rodada termina.
Implementado como a pausa descrita em §5.3 (passo 5a) e na tela 1b de §5.5.

O que continua valendo do resto: **erro do worker** ⇒ a rodada para sem perguntar
(a etapa está quebrada); **sessão expirada no meio** ⇒ a etapa termina
normalmente e as escolas afetadas vão para a planilha de "não coletadas".
