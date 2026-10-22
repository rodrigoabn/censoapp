# Coleta Automática — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nova aplicação no grupo "Coleta do Educacenso" que roda as 6 etapas de coleta em sequência, em background, com credenciais digitadas uma vez, e entrega um ZIP único com o tempo de cada etapa.

**Architecture:** Três módulos novos em `apps/coleta_automatica/`: `etapas.py` (registro das 6 etapas, reusando os `config`/`worker`/`zipper` dos coletores existentes), `runner.py` (a rodada em thread, a classificação das etapas e o pacote final) e `frontend.py` (a tela nos 5 estados). Nenhum dos 6 coletores é alterado: a rodada **chama** o worker de cada app, que abre o navegador, faz o login e grava os arquivos da etapa exatamente como na tela dela.

**Tech Stack:** Python 3.14, Streamlit 1.58 (`playwright.sync_api` via os coletores), `threading` para a rodada, `zipfile` para o pacote, `pytest` + `streamlit.testing.v1.AppTest`.

**Spec:** `docs/historico/superpowers/specs/2026-10-20-coleta-automatica-design.md` — o plano implementa o spec; leia os dois.

## Global Constraints

- **Não alterar** o comportamento, o `auth.py`, o `scraper.py`, o `exporter.py`/`zipper.py` nem o `frontend.py` dos 6 coletores existentes.
- **Modo leitura:** nada de escrita no Educacenso; `READ_ONLY = True` vale para todos os coletores.
- **Série, nunca paralelo:** as etapas rodam em sequência, uma por vez, na ordem do registro.
- **Sessão do Educacenso:** cada etapa faz o próprio login (não há sessão compartilhada).
- **Rótulos e cores:** botão de ação único chamado **Executar**, em azul (`--status-info` = `#1e4482`); todo botão de download em azul; cabeçalho padrão e card "Orientações de uso" via `apps/common/banner.py` e `apps/common/orientacoes.py`; relógio via `RELOGIO_CSS` e os helpers de `apps/common/ui.py`.
- **Credenciais nunca em disco:** CPF e senha ficam em memória (estado da sessão do Streamlit).
- **Prefixo de estado da nova tela:** `ca_` (nenhuma outra app usa esse prefixo).
- **Sem `st.form`** nesta tela: o botão "Executar" fica no fim das opções selecionáveis, fora de qualquer formulário (`st.button` e `st.download_button` são proibidos dentro de `st.form` no Streamlit 1.58).
- **Idioma:** textos de interface e mensagens em português.

## Review Focus

Comportamentos que uma pessoa usaria de verdade e que nenhum teste de tarefa acima exercise — cada um ganha o teste indicado:

1. **Nenhuma aplicação marcada** → o clique em "Executar" não pode iniciar a rodada: mostrar erro e não criar thread. → Task 4, `test_executar_sem_aplicacao_mostra_erro`.
2. **CPF ou senha vazios** → erro "Preencha login e senha" e nenhuma thread criada. → Task 4, `test_executar_sem_credenciais_mostra_erro`.
3. **Planilha sem a coluna "código do inep"** → o erro do `read_school_list` aparece na tela e a rodada não começa. → Task 4, `test_lista_invalida_mostra_erro`.
4. **A rodada termina com 0 escola coletada** → o pacote completo **não** é gerado, e as etapas concluídas continuam baixáveis uma a uma. → Task 2, `test_rodada_sem_coleta_nao_gera_pacote`.
5. **O usuário navega para outra tela no meio da rodada** → `hub_sessao.liberar_execucoes` sinaliza o `Event` de parada; a rodada para na etapa corrente e a etapa é marcada "Interrompida". → Task 2, `test_interrupcao_entre_etapas_marca_nao_executada`.

---

### Task 1: Registro das 6 etapas

**Files:**
- Create: `apps/coleta_automatica/__init__.py` (vazio)
- Create: `apps/coleta_automatica/src/__init__.py` (vazio)
- Create: `apps/coleta_automatica/src/etapas.py`
- Test: `tests/test_coleta_automatica_etapas.py`

**Interfaces:**
- Consumes: `apps.coleta_cadastros_escolas.src.frontend` (CONFIG, `_ctx()`), `apps.coleta_gestor.src.frontend` (CONFIG, `_ctx()`), `apps.coleta_relatorios.src.frontend` (`_ctx()`), `apps.coleta_relatorios.src.reports.REPORTS`, `apps.coleta_recibos_fechamento.src.frontend` (CONFIG, `_ctx()`).
- Produces:
  ```python
  @dataclass(frozen=True)
  class Etapa:
      chave: str        # "cadastros_escolas"
      titulo: str       # "Cadastros das escolas"
      pasta: str        # "cadastros_escolas" (nome da pasta no ZIP final)
      config: dict      # o config do app de origem
      zipper: Any       # módulo exporter/zipper do app
      worker: Callable  # (config, login, senha, escolas, stop_event, lock, shared, tmp_dir)
      textos: Any       # TextosFrontend do app

  ETAPAS: tuple[Etapa, ...]   # as 6, na ordem da rodada
  def etapa_por_chave(chave: str) -> Etapa   # levanta KeyError se não existir
  ```

- [ ] **Step 1: Write the failing test**

`tests/test_coleta_automatica_etapas.py`:

```python
"""Registro das 6 etapas da Coleta Automática."""

from __future__ import annotations

import pytest

from apps.coleta_automatica.src.etapas import ETAPAS, etapa_por_chave


def test_registro_tem_as_seis_etapas_na_ordem_da_rodada():
    assert [e.chave for e in ETAPAS] == [
        "cadastros_escolas",
        "gestor",
        "relatorios_turmas",
        "relatorios_alunos",
        "relatorios_profissionais",
        "recibos",
    ]
    assert [e.titulo for e in ETAPAS] == [
        "Cadastros das escolas",
        "Cadastro do gestor",
        "Relatórios de Turmas",
        "Relatórios de Alunos",
        "Relatórios de Profissionais Escolares",
        "Recibos de Fechamento",
    ]


def test_cada_etapa_aponta_para_o_app_de_origem():
    by_chave = {e.chave: e for e in ETAPAS}
    assert by_chave["cadastros_escolas"].config["state_prefix"] == "ws_"
    assert by_chave["cadastros_escolas"].config["zip_prefix"] == "cadastro_escola"
    assert by_chave["gestor"].config["state_prefix"] == "cg_"
    assert by_chave["gestor"].config["zip_prefix"] == "vinculo_gestor"
    assert by_chave["relatorios_turmas"].config["state_prefix"] == "rt_"
    assert by_chave["relatorios_alunos"].config["state_prefix"] == "ra_"
    assert by_chave["relatorios_profissionais"].config["state_prefix"] == "rp_"
    assert by_chave["recibos"].config["state_prefix"] == "rf_"


def test_worker_de_cada_etapa_aceita_o_config_primeiro():
    import inspect

    for etapa in ETAPAS:
        params = list(inspect.signature(etapa.worker).parameters)
        assert params[0] == "config", (etapa.chave, params)
        assert params[1:4] == ["login", "senha", "escolas"], (etapa.chave, params)


def test_zipper_de_cada_etapa_monta_o_artefato():
    for etapa in ETAPAS:
        construtor = etapa.config.get("construtor_arquivo", "build_zip")
        assert hasattr(etapa.zipper, construtor), (etapa.chave, construtor)
        assert hasattr(etapa.zipper, "output_filename")


def test_etapa_por_chave():
    assert etapa_por_chave("gestor").titulo == "Cadastro do gestor"
    with pytest.raises(KeyError):
        etapa_por_chave("inexistente")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_coleta_automatica_etapas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'apps.coleta_automatica'`

- [ ] **Step 3: Implement `apps/coleta_automatica/src/etapas.py`**

Crie `apps/coleta_automatica/__init__.py` e `apps/coleta_automatica/src/__init__.py` vazios.

Em `etapas.py`, defina o dataclass `Etapa` (campos exatos da seção Interfaces) e monte `ETAPAS` chamando o `_ctx()` de cada app de origem para obter `scrape_worker`, `zipper` e `textos` — o `_ctx()` de cada app já devolve esses três campos wired, e `REPORTS`/`CONFIG` dão o `config`. Os prefixos de estado e `zip_prefix` são os de cada app: `ws_`/`cadastro_escola`, `cg_`/`vinculo_gestor`, `rt_`/`relatorio_turmas`, `ra_`/`relatorio_alunos`, `rp_`/`relatorio_profissionais`, `rf_`/`recibos_fechamento`.

`pasta` (nome da pasta no ZIP final) = `cadastros_escolas`, `gestor`, `relatorios_turmas`, `relatorios_alunos`, `relatorios_profissionais`, `recibos`.

Deixe um comentário no topo de `etapas.py` registrada: o `_ctx()` dos apps é privado por herança da Fase 4; importar o `_ctx()` em vez de tocar nos 6 coletores foi escolha deliberada (o spec proíbe alterá-los).

`etapa_por_chave(chave)` indexa `ETAPAS` e levanta `KeyError` se não achar.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_coleta_automatica_etapas.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add apps/coleta_automatica tests/test_coleta_automatica_etapas.py
git commit -m "feat: registro das 6 etapas da Coleta Automática"
```

---

### Task 2: A rodada em thread

**Files:**
- Create: `apps/coleta_automatica/src/runner.py`
- Test: `tests/test_coleta_automatica_runner.py`

**Interfaces:**
- Consumes: `Etapa` e `ETAPAS` de Task 1; `apps.common.export.remove_temp`.
- Produces:
  ```python
  SITUACOES = ("pendente", "em_andamento", "concluida", "concluida_sem_dados",
                "falhou", "interrompida", "nao_executada")

  @dataclass
  class ResultadoEtapa:
      chave: str
      titulo: str
      situacao: str
      segundos: float
      caminho_artefato: str | None
      caminho_pendencias: str | None
      motivo: str | None

  def executar_rodada(etapas, login, senha, escolas, *, stop_event, lock, estado,
                      pasta_base, continuar_event=None) -> None
  ```
  `estado` é o dicionário da rodada, atualizado sob `lock`, com as chaves:
  `etapa_atual` (chave ou None), `shared_etapa` (o `shared` da etapa em curso, para a
  linha viva), `resultados` (lista de `ResultadoEtapa`, na ordem das etapas),
  `aguardando` (chave da etapa que paused a rodada ou None), `interrompida` (bool),
  `pacote` (`(caminho, nome)` ou None — preenchido pela Task 3).

- [ ] **Step 1: Write the failing test**

`tests/test_coleta_automatica_runner.py` — use uma etapa falsa (não chama navegador):

```python
"""A rodada da Coleta Automática: sequência, tempos, falhas e interrupção."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from apps.coleta_automatica.src.etapas import Etapa
from apps.coleta_automatica.src.runner import executar_rodada


class _ZipperFalso:
    """Constrói um 'artefato' de mentira e knows os nomes."""

    def output_filename(self, prefix):
        return f"{prefix}_fake.bin"

    def pending_filename(self, prefix):
        return f"{prefix}_nao_coletadas_fake.xlsx"

    def build_xlsx(self, tmp_dir, model=None):
        return b"artefato-falso"

    def build_zip(self, tmp_dir):
        return b"artefato-falso"


def _etapa(chave, *, erro=None, coletadas=2, arquivos=("dados.csv",)):
    """Etapa falsa: o worker grava arquivos e preenche o shared como o real."""

    def worker(config, login, senha, escolas, stop_event, lock, shared, tmp_dir):
        shared["total"] = len(escolas)
        for nome in arquivos:
            (Path(tmp_dir) / nome).write_text("x", encoding="utf-8")
        if erro:
            shared["error"] = erro
        shared["count"] = coletadas
        shared["failures"] = [] if coletadas else [
            {"codigo_inep": "33000001", "nome_unidade": "Escola Um", "motivo": "Falha no login"}
        ]

    return Etapa(
        chave=chave, titulo=chave, pasta=chave, config={"zip_prefix": chave},
        zipper=_ZipperFalso(), worker=worker, textos=None,
    )


def _rodar(etapas, *, stop_event=None, continuar_event=None, tmp_path=None):
    estado = {"resultados": [], "etapa_atual": None, "shared_etapa": None,
              "aguardando": None, "interrompida": False, "pacote": None}
    executar_rodada(
        etapas, "cpf", "senha", [{"codigo_inep": "33000001", "nome_unidade": "Escola Um"}],
        stop_event=stop_event or threading.Event(),
        lock=threading.Lock(),
        estado=estado,
        pasta_base=tmp_path,
        continuar_event=continuar_event,
    )
    return estado


def test_rodada_roda_as_etapas_em_sequencia_e_mede_os_tempos(tmp_path):
    estado = _rodar([_etapa("a"), _etapa("b")], tmp_path=tmp_path)
    assert [r.chave for r in estado["resultados"]] == ["a", "b"]
    assert all(r.situacao == "concluida" for r in estado["resultados"])
    assert all(r.segundos >= 0 for r in estado["resultados"])
    assert all(r.caminho_artefato for r in estado["resultados"])


def test_artefato_de_cada_etapa_vai_para_o_disco(tmp_path):
    estado = _rodar([_etapa("a")], tmp_path=tmp_path)
    caminho = Path(estado["resultados"][0].caminho_artefato)
    assert caminho.exists()


def test_etapa_com_erro_do_worker_derruba_a_rodada(tmp_path):
    estado = _rodar([_etapa("a", erro="browser morreu"), _etapa("b")], tmp_path=tmp_path)
    assert estado["resultados"][0].situacao == "falhou"
    assert estado["resultados"][0].motivo == "browser morreu"
    assert estado["resultados"][1].situacao == "nao_executada"
    assert estado["interrompida"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_coleta_automatica_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'apps.coleta_automatica.src.runner'`

- [ ] **Step 3: Implement `apps/coleta_automatica/src/runner.py`**

Implemente `executar_rodada` com esta sequência, para **cada** etapa de `etapas`:

1. Se `stop_event.is_set()`: marque as etapas restantes como `nao_executada`, interrompa o laço.
2. Crie a pasta da etapa: `pasta_base / etapa.chave` (`mkdir(parents=True, exist_ok=True)`).
3. Crie `shared` com as chaves `current`, `last`, `count`, `total`, `done`, `error`, `interrupted`, `failures` (todas None/0/False/[] como no `worker_base`).
4. Publique em `estado["etapa_atual"] = etapa.chave` e `estado["shared_etapa"] = shared` (o **objeto**, não uma cópia — a tela lê `current`/`last` dele).
5. Marque a etapa como `em_andamento` e registre `t0 = time.monotonic()`.
6. Chame `etapa.worker(etapa.config, login, senha, escolas, stop_event, lock, shared, pasta_etapa)`.
7. `segundos = time.monotonic() - t0`.
8. Classifique:
   - `shared.get("error")` preenchido → `situacao="falhou"`, `motivo=shared["error"]`, e a rodada para (as restantes viram `nao_executada`, `estado["interrompida"] = True`).
   - `shared.get("count", 0) == 0` → `situacao="concluida_sem_dados"`, **sem** artefato, e a rodada **pausa**: publique `estado["aguardando"] = etapa.chave` e espere em laço (`continuar_event.wait(0.5)` revalidando `stop_event.is_set()`) até `continuar_event` ser disparado; se `stop_event` for sinalizado nesse meio, marque a etapa como `interrompida` e pare. Ao ser liberado, siga para a próxima etapa.
   - caso contrário → `situacao="concluida"`: monte o artefato com `getattr(etapa.zipper, etapa.config.get("construtor_arquivo", "build_zip"))(tmp_dir=pasta_etapa)` e grave-o em `pasta_base / etapa.pasta / etapa.zipper.output_filename(etapa.config["zip_prefix"])`; se `shared.get("failures")`, grave também a planilha de pendências com `apps.common.export.build_pending_xlsx(failures)` em `pasta_base / etapa.pasta / etapa.zipper.pending_filename(etapa.config["zip_prefix"])`.
9. Ao final, remova a pasta temporária da etapa (`apps.common.export.remove_temp(pasta_etapa)`) e publique `estado["etapa_atual"] = None`.

O runner **não** toca em `st.*` e **não** gera o pacote (Task 3).

- [ ] **Step 4: Run test to verify it fails (a parte da pausa)**

Adicione ao mesmo arquivo:

```python
def test_etapa_sem_coleta_pausa_a_rodada_e_espera_confirmacao(tmp_path):
    continuar = threading.Event()
    estado = {}
    lock = threading.Lock()

    def rodar():
        executar_rodada(
            [_etapa("a", coletadas=0), _etapa("b")], "cpf", "senha",
            [{"codigo_inep": "33000001", "nome_unidade": "Escola Um"}],
            stop_event=threading.Event(), lock=lock, estado=estado,
            pasta_base=tmp_path, continuar_event=continuar,
        )

    t = threading.Thread(target=rodar, daemon=True)
    t.start()
    for _ in range(100):
        if estado.get("aguardando"):
            break
        time.sleep(0.05)
    assert estado["aguardando"] == "a"
    assert [r.situacao for r in estado["resultados"]] == ["concluida_sem_dados"]
    assert t.is_alive()  # a rodada está esperando o usuário

    continuar.set()
    t.join(timeout=10)
    assert [r.situacao for r in estado["resultados"]] == ["concluida_sem_dados", "concluida"]
```

Run: `uv run python -m pytest tests/test_coleta_automatica_runner.py -v`
Expected: PASS (a implementação do passo 3 já cobre a pausa)

- [ ] **Step 5: Adicione o teste da interrupção e rode**

```python
def test_interrupcao_entre_etapas_marca_nao_executada(tmp_path):
    stop = threading.Event()
    stop.set()
    estado = _rodar([_etapa("a"), _etapa("b")], stop_event=stop, tmp_path=tmp_path)
    assert [r.situacao for r in estado["resultados"]] == ["nao_executada", "nao_executada"]
    assert estado["interrompida"] is True
```

Run: `uv run python -m pytest tests/test_coleta_automatica_runner.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add apps/coleta_automatica/src/runner.py tests/test_coleta_automatica_runner.py
git commit -m "feat: rodada sequencial das coletas em background"
```

---

### Task 3: O pacote completo

**Files:**
- Modify: `apps/coleta_automatica/src/runner.py`
- Test: `tests/test_coleta_automatica_runner.py`

**Interfaces:**
- Consumes: `ResultadoEtapa` e o `estado` de Task 2.
- Produces:
  ```python
  def montar_pacote(resultados: list[ResultadoEtapa], pasta_base: Path) -> Path
      # devolve o caminho do ZIP criado; None se não houver nenhum artefato
  ```
  O ZIP se chama `coleta_completa_DD-MM-AAAA.zip` (use `apps.common.export.output_filename("coleta_completa", ext=".zip")`), criado dentro de `pasta_base`.

- [ ] **Step 1: Write the failing test**

```python
def test_pacote_completo_reune_os_artefatos_em_pastas(tmp_path):
    from apps.coleta_automatica.src.runner import montar_pacote

    estado = _rodar([_etapa("a"), _etapa("b")], tmp_path=tmp_path)
    zip_path = montar_pacote(estado["resultados"], tmp_path)
    assert zip_path is not None and zip_path.exists()

    import zipfile
    with zipfile.ZipFile(zip_path) as z:
        nomes = z.namelist()
    assert any(n.startswith("a/") for n in nomes)
    assert any(n.startswith("b/") for n in nomes)


def test_rodada_sem_coleta_nao_gera_pacote(tmp_path):
    estado = _rodar([_etapa("a", coletadas=0)], tmp_path=tmp_path)
    assert estado["resultados"][0].caminho_artefato is None
    assert estado["pacote"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_coleta_automatica_runner.py -k pacote -v`
Expected: FAIL — `ImportError: cannot import name 'montar_pacote'`

- [ ] **Step 3: Implement `montar_pacote` e chame-o no fim da rodada**

`montar_pacote(resultados, pasta_base)`:
- Se nenhum resultado tiver `caminho_artefato`, devolve `None`.
- Cria o ZIP em `pasta_base / output_filename("coleta_completa", ext=".zip")` (`apps.common.export.output_filename`).
- Para cada resultado com artefato, grava o arquivo em `<pasta>/<chave>/<nome do arquivo>` (o nome vem do `Path(caminho_artefato).name`); a pasta dentro do ZIP é o `chave` do resultado.
- Se o resultado tiver `caminho_pendencias`, grava a planilha na mesma pasta.

No fim de `executar_rodada` (só quando a rodada **não** foi interrompida e houve ao menos um artefato), chame `montar_pacote` e publique `estado["pacote"] = (str(caminho), nome)`. Se a rodada foi interrompida ou alguma etapa falhou, `estado["pacote"]` continua `None`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_coleta_automatica_runner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/coleta_automatica/src/runner.py tests/test_coleta_automatica_runner.py
git commit -m "feat: pacote único com os artefatos de todas as etapas"
```

---

### Task 4: A tela

**Files:**
- Create: `apps/coleta_automatica/src/frontend.py`
- Test: `tests/test_coleta_automatica_frontend.py`

**Interfaces:**
- Consumes: `etapas.ETAPAS`, `runner.executar_rodada`, `apps.common.ui.{RELOGIO_CSS, _duracao, _horario, _relogio_andamento_html, _relogio_resumo_html}`, `apps.common.banner.banner_titulo`, `apps.common.orientacoes.card_orientacoes`, `apps.common.school_list.read_school_list`, `apps.common.export.output_filename`.
- Produces: `render_coleta_automatica_frontend(logo_base64: str | None = None) -> None`.

Chaves de sessão (prefixo `ca_`): `ca_running`, `ca_stop` (Event), `ca_continuar` (Event), `ca_lock` (Lock), `ca_estado` (dict), `ca_thread`, `ca_finalized` (bool), `ca_inicio` (datetime), `ca_fim` (datetime), `ca_pasta` (Path).

A seleção das etapas vive nas próprias chaves dos checkboxes (`ca_sel_<chave>`) — não há chave de seleção separada. O caminho do pacote fica em `ca_estado["pacote"]` (a thread não escreve no `session_state`; o spec §5.4 previa `ca_zip`, dispensado por isso).

- [ ] **Step 1: Write the failing test**

`tests/test_coleta_automatica_frontend.py` — com `AppTest`:

```python
"""A tela da Coleta Automática: formulário, seleção e estados da rodada."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

_RAIZ = Path(__file__).resolve().parents[1]


def _script():
    import streamlit as st

    from apps.coleta_automatica.src.frontend import render_coleta_automatica_frontend

    render_coleta_automatica_frontend()


def _app():
    return AppTest.from_function(_script, default_timeout=60).run()


def test_formulario_tem_credenciais_lista_e_selecao():
    at = _app()
    assert not at.exception
    rotulos = [t.label for t in at.text_input]
    assert any("Login" in r for r in rotulos)
    assert any("Senha" in r for r in rotulos)
    assert len(at.file_uploader) == 1
    # 6 opções selecionáveis + 1 botão Executar
    assert len(at.checkbox) == 6
    assert any(b.label == "Executar" for b in at.button)
    assert all(c.value for c in at.checkbox)  # todas marcadas por padrão


def test_executar_sem_aplicacao_mostra_erro():
    at = _app()
    for c in at.checkbox:
        c.uncheck()
    at.button(key="ca_executar").click().run()
    assert not at.exception
    assert any("aplica" in e.value.lower() for e in at.error)


def test_executar_sem_credenciais_mostra_erro():
    at = _app()
    at.button(key="ca_executar").click().run()
    assert not at.exception
    assert any("login" in e.value.lower() for e in at.error)


def test_lista_invalida_mostra_erro():
    import io

    import openpyxl

    at = _app()
    wb = openpyxl.Workbook()
    wb.active.append(["coluna errada"])
    buf = io.BytesIO()
    wb.save(buf)
    at.file_uploader[0].upload("escolas.xlsx", buf.getvalue())
    at.text_input(key="ca_login").set_value("123")
    at.text_input(key="ca_senha").set_value("x")
    at.button(key="ca_executar").click().run()
    assert not at.exception
    assert at.error
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_coleta_automatica_frontend.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'apps.coleta_automatica.src.frontend'`

- [ ] **Step 3: Implement `apps/coleta_automatica/src/frontend.py` — estado 0 (formulário)**

Estrutura da tela (rascunho v5 aprovado):

1. `banner_titulo(st, "Coleta Automática", "Executa em sequência as coletas do Educacenso, em segundo plano.", logo_base64)`.
2. Card de **Orientações de uso** em largura total, com `card_orientacoes(st, corpo=...)` e os 5 passos: credenciais, lista, marcar as aplicações, Executar, downloads.
3. Card **Acesso ao Educacenso** em largura total: `st.text_input("Login (CPF)", key="ca_login")`, `st.text_input("Senha", type="password", key="ca_senha")` e `st.file_uploader("Lista de escolas (.xlsx / .xls)", type=["xlsx", "xls"], key="ca_lista")`, os três lado a lado (`st.columns(3)`).
4. Card **Aplicações a coletar** em largura total: um `st.checkbox` por etapa de `ETAPAS`, com `key=f"ca_sel_{etapa.chave}"` e `value=True`; o texto do checkbox é o `etapa.titulo`. Mostre o contador "N de 6 aplicações selecionadas" e, no fim das opções, `st.button("Executar", type="primary", key="ca_executar")`.

Ao clicar em "Executar" (fora de qualquer `st.form`):

- Se **nenhuma** aplicação estiver marcada → `st.error("Selecione ao menos uma aplicação para coletar.")` e **não** iniciar nada.
- Se CPF ou senha estiverem vazios → `st.error("Preencha login e senha.")` e não iniciar nada.
- Se a lista não foi enviada → `st.error("Envie a lista de escolas.")` e não iniciar nada.
- `read_school_list` pode levantar `ValueError` → mostre `st.error(str(exc))` e não iniciar nada.
- Caso contrário: crie `ca_stop` (Event), `ca_continuar` (Event), `ca_lock` (Lock), `ca_pasta` (`Path(tempfile.mkdtemp(prefix="coleta_automatica_tmp_"))`), `ca_estado` (dict vazio com as chaves de `estado`), `ca_inicio` (`datetime.now()`), `ca_selecionadas` (as chaves marcadas), `ca_running=True`, `ca_finalized=False`; suba a thread com `threading.Thread(target=executar_rodada, args=(etapas_selecionadas, login, senha, escolas), kwargs={...}, daemon=True)`; `st.rerun()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_coleta_automatica_frontend.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/coleta_automatica/src/frontend.py tests/test_coleta_automatica_frontend.py
git commit -m "feat: formulário da Coleta Automática com seleção de aplicações"
```

---

### Task 5: A tela da rodada (relógio, tabela por etapa, estados)

**Files:**
- Modify: `apps/coleta_automatica/src/frontend.py`
- Test: `tests/test_coleta_automatica_frontend.py`

**Interfaces:**
- Consumes: `ResultadoEtapa` e `SITUACOES` de Task 2; `RELOGIO_CSS`, `_duracao`, `_horario`, `_relogio_andamento_html`, `_relogio_resumo_html`, `linha_monitor`, `status_color` de `apps.common.ui`.
- Produces: nada novo — completa `render_coleta_automatica_frontend` com os estados 1, 1b, 2 e 3.

- [ ] **Step 1: Write the failing test**

Em `tests/test_coleta_automatica_frontend.py`, acrescente (use a classe real `ResultadoEtapa`, não dict):

```python
def test_estado_concluido_mostra_tabela_e_pacote():
    from datetime import datetime

    from apps.coleta_automatica.src.runner import ResultadoEtapa

    at = _app()
    at.session_state["ca_running"] = False
    at.session_state["ca_finalized"] = True
    at.session_state["ca_inicio"] = datetime(2026, 10, 20, 21, 15, 3)
    at.session_state["ca_fim"] = datetime(2026, 10, 20, 21, 34, 50)
    at.session_state["ca_estado"] = {
        "resultados": [
            ResultadoEtapa(chave="gestor", titulo="Cadastro do gestor",
                           situacao="concluida", segundos=48.0,
                           caminho_artefato=None, caminho_pendencias=None,
                           motivo=None),
        ],
        "etapa_atual": None, "shared_etapa": None, "aguardando": None,
        "interrompida": False, "pacote": None,
    }
    at.run()
    assert not at.exception
    assert any("Tempo de execução" in m.value for m in at.markdown)
    assert any("Cadastro do gestor" in m.value for m in at.markdown)


def test_estado_interrompido_avisa_que_nao_ha_pacote():
    at = _app()
    at.session_state["ca_running"] = False
    at.session_state["ca_finalized"] = True
    at.session_state["ca_estado"] = {
        "resultados": [], "etapa_atual": None, "shared_etapa": None,
        "aguardando": None, "interrompida": True, "pacote": None,
    }
    at.run()
    assert not at.exception
    assert any("interrompida" in m.value.lower() for m in at.markdown)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_coleta_automatica_frontend.py -k estado -v`
Expected: FAIL — o estado de resultado ainda não é desenhado.

- [ ] **Step 3: Implemente os estados 1 (em andamento), 1b (pausa), 2 (concluída) e 3 (interrompida)**

Quando `ca_running` for verdadeiro, a tela desenha (nunca `st.form`):

- `st.markdown(RELOGIO_CSS, unsafe_allow_html=True)`.
- O **relógio digital**: `st.markdown(_relogio_andamento_html((datetime.now() - ca_inicio).total_seconds(), ca_inicio), unsafe_allow_html=True)`.
- A tabela **Tempo por aplicação**: para cada resultado em `ca_estado["resultados"]`, uma fileira de `st.columns([3, 1.6, 1, 2.6, 1])` com o título, a situação (colorida: `concluida` verde `#22c55e`, `falhou` vermelho `#ef4444`, `em_andamento` azul `#93c5fd`, `concluida_sem_dados`/`interrompida` em `#eab308`, `pendente`/`nao_executada` cinza `#8b8f99`), o tempo (`_duracao(segundos)`), o resultado (o nome do arquivo ou o motivo) e o botão de download (`st.download_button("Baixar", data=<callable que lê o arquivo>, file_name=..., mime=...)` — o `data` é um **callable** para materializar o arquivo só no clique) quando houver artefato; quando houver planilha de pendências, um segundo botão "Pendências".
- A linha viva: se `ca_estado["shared_etapa"]` tiver `current`, mostre "Escola X (código) coletando…" (use `apps.common.ui.linha_monitor` e `status_color`).
- O botão **"⛔ Interromper rodada"** (`key="ca_interromper"`), que apenas marca `ca_stop` (o `stop_check` do coletor encerra com segurança).
- Se `ca_estado["aguardando"]` não for `None`: mostre a informação "A etapa X não coletou nenhuma escola" e os botões **"Continuar"** (`key="ca_continuar"` → `ca_continuar.set()`) e **"Encerrar a rodada"** (`key="ca_encerrar"` → `ca_stop.set()`).

Quando `ca_running` for falso e `ca_finalized` for verdadeiro:

- `ca_fim` (datetime) e o resumo com `_relogio_resumo_html(ca_inicio, ca_fim)`.
- A tabela completa (mesma estrutura do estado em andamento, agora sem o botão de interromper).
- Se `ca_estado["pacote"]` existir: o cartão **Pacote completo** com `st.download_button("Baixar ZIP com todas as coletas", data=<callable>, file_name=<nome>, mime="application/zip")`.
- Se não existir: o aviso em vermelho "Rodada interrompida — o pacote completo não é gerado." e a nota de que as etapas concluídas continuam baixáveis uma a uma.
- O botão **"Nova rodada"** (`key="ca_nova_rodada"`): volta ao formulário preservando credenciais e seleção (limpe `ca_running`, `ca_finalized`, `ca_estado`, `ca_pasta`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_coleta_automatica_frontend.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/coleta_automatica/src/frontend.py tests/test_coleta_automatica_frontend.py
git commit -m "feat: relógio e tempo por etapa na tela da rodada"
```

---

### Task 6: Menu e roteamento

**Files:**
- Modify: `app.py` (import, `_MENU_GROUPS`, roteamento)
- Modify: `tests/test_hub_navegacao.py`

**Interfaces:**
- Consumes: `render_coleta_automatica_frontend` de Task 4.
- Produces: item de menu `"Coleta Automática"` no grupo `"Coleta do Educacenso"`, **primeiro** da lista; a chave do botão de menu segue o padrão `f"nav_{_grupo}_{_i}"` (o novo item é `nav_Coleta do Educacenso_0`).

- [ ] **Step 1: Write the failing test**

Em `tests/test_hub_navegacao.py`, troque o acesso **por índice** dos botões do menu por acesso **por rótulo** (a inserção do item novo no topo do grupo desloca os índices) e acrescente o teste da nova página:

```python
def _botao_do_menu(at, rotulo):
    for botao in at.button:
        if (botao.label or "").strip() == rotulo:
            return botao
    raise AssertionError(f"botão {rotulo!r} não encontrado no menu")


def test_navegacao_troca_pagina_e_limpa_estado(monkeypatch):
    at = _novo_app(monkeypatch)
    at.session_state["estado_da_pagina_anterior"] = "x"

    _botao_do_menu(at, "Dados Cadastrais das Unidades").click().run()
    assert at.session_state["nav_page"] == "Dados Cadastrais das Unidades"
    assert at.session_state["prev_nav_page"] == "Dados Cadastrais das Unidades"
    assert "estado_da_pagina_anterior" not in at.session_state

    at.session_state["segundo_estado"] = "y"
    _botao_do_menu(at, "Dados dos Gestores Escolares").click().run()
    assert at.session_state["nav_page"] == "Dados dos Gestores Escolares"
    assert at.session_state["prev_nav_page"] == "Dados dos Gestores Escolares"
    assert "segundo_estado" not in at.session_state
    assert not at.exception


def test_menu_tem_a_coleta_automatica(monkeypatch):
    at = _novo_app(monkeypatch)
    _botao_do_menu(at, "Coleta Automática").click().run()
    assert not at.exception
    assert at.session_state["nav_page"] == "Coleta Automática"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_hub_navegacao.py -v`
Expected: FAIL — `AssertionError: botão 'Coleta Automática' não encontrado no menu`

- [ ] **Step 3: Implementar o item de menu e o roteamento em `app.py`**

- Import: `from apps.coleta_automatica.src.frontend import render_coleta_automatica_frontend` (entre os imports de `apps.*`, em ordem alfabética de caminho).
- Em `_MENU_GROUPS["Coleta do Educacenso"]`, placing `"Coleta Automática"` **primeiro** da lista.
- No roteamento, antes do `elif page == "Tela Inicial"`: `elif page == "Coleta Automática": render_coleta_automatica_frontend(logo_base64); render_license_footer()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_hub_navegacao.py -v`
Expected: PASS

- [ ] **Step 5: Rode a suíte inteira**

Run: `uv run python -m pytest -q`
Expected: PASS (657 testes existentes + os novos, sem regressão)

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_hub_navegacao.py
git commit -m "feat: Coleta Automática no menu de Coleta do Educacenso"
```

---

### Task 7: Documentação

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/historico/plano_de_melhoria.md`
- Modify: `apps/inicio/documentacao.py`

**Interfaces:**
- Consumes: nada de código novo.
- Produces: nada de código novo.

- [ ] **Step 1: Write the failing test**

Em `tests/test_inicio_documentacao.py`, acrescente:

```python
def test_documentacao_menciona_a_coleta_automatica():
    from apps.inicio.documentacao import build_documentacao_pdf

    pdf = build_documentacao_pdf()
    assert pdf.startswith(b"%PDF")
```

Run: `uv run python -m pytest tests/test_inicio_documentacao.py -v`
Expected: PASS já (o smoke não inspeciona o texto) — este passo é só o guarda de que o PDF continua gerando.

- [ ] **Step 2: Atualize `AGENTS.md`**

- Na lista de apps: acrescente `coleta_automatica/` — roda as 6 coletas em sequência e gera um ZIP único.
- Na lista de `apps/common/`, nenhuma mudança (a skill não cria módulo novo em `common`).
- Na seção de layout, acrescente uma linha: a Coleta Automática usa o mesmo cabeçalho, o card de Orientações e o relógio, com o tempo particionado por aplicação.

- [ ] **Step 3: Atualize `docs/historico/plano_de_melhoria.md`**

Acrescente a seção **"## Fase 7 — Coleta Automática"**, seguindo o formato das fases anteriores (lista de itens, foco da revisão e uma linha de status), registrando: a aplicação nova, o arquivo do design (`docs/historico/superpowers/specs/2026-10-20-coleta-automatica-design.md`) e o branch `automacao-coleta`.

- [ ] **Step 4: Atualize o PDF de documentação (`apps/inicio/documentacao.py`)**

- Na tabela da Visão Geral (seção 1), acrescente a linha da nova aplicação, no grupo "Coleta do Educacenso": `["Coleta do Educacenso", "Coleta Automática", "Roda as 6 coletas do Educacenso em sequência, em segundo plano, e gera um ZIP único com os artefatos e o tempo de cada etapa."]`.
- Na seção 6 (Aplicações de Coleta de Dados), acrescente um parágrafo curto sobre a aplicação, no padrão dos parágrafos existentes da seção (o que entra, o que produz, o relógio com o tempo por aplicação).
- Bump da versão na capa: `Versão: 1.1` → `Versão: 1.2`.

- [ ] **Step 5: Verifique o PDF e a suíte**

```bash
uv run python -c "
from apps.inicio.documentacao import build_documentacao_pdf
pdf = build_documentacao_pdf()
open('/tmp/documentacao.pdf','wb').write(pdf)
print(len(pdf))
"
pdftotext -layout /tmp/documentacao.pdf - | grep -c "Coleta Automática"
uv run python -m pytest -q
```

Expected: o PDF gera, o grep encontra 1+ ocorrências, a suíte passa.

- [ ] **Step 6: Commit**

```bash
git add AGENTS.md docs/historico/plano_de_melhoria.md apps/inicio/documentacao.py tests/test_inicio_documentacao.py
git commit -m "docs: Coleta Automática no AGENTS, no plano e no manual do usuário"
```

---

## Verificação final da branch

Ao terminar, rode:

```bash
uv run ruff check .
uv run python -m pytest -q
uv run streamlit run app.py --server.port <porta> --server.headless true
```

E confirme na tela: o item "Coleta Automática" aparece no grupo "Coleta do Educacenso"; o formulário mostra credenciais, lista, as 6 opções marcadas e o botão "Executar" no fim; a rodada mostra o relógio digital e a tabela de tempos por etapa; a etapa sem coleta pausa com a pergunta; a rodada completa entrega o "Baixar ZIP com todas as coletas".
