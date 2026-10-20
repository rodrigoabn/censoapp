# Execução local — HUB de Aplicações de Apoio (Censo Escolar)

Runbook para rodar o HUB no servidor local **sem Docker**, usando apenas o
`uv` para criar o ambiente e o Streamlit para servir a aplicação.

## 1. Modelo de operação

```text
navegador ──http──► Streamlit :<porta>   (servidor local)
                         ├─ Playwright/Chromium instalado no host
                         ├─ ./logs/censoapp.log (log rotativo)
                         └─ /tmp/educacenso_*_tmp_ (temporários da coleta)
```

- A aplicação é usada **5 a 15 vezes por ano**, ficando no ar por **5 a 7 dias**
  em cada janela.
- O operador sobe e derruba manualmente com `uv run streamlit run app.py` e
  escolhe a porta no momento (`--server.port`; padrão 8501).
- **Sem Docker, sem Caddy e sem autenticação própria do HUB.** A aplicação é
  servida em **HTTP puro**; o acesso é controlado pela rede (firewall/VPN) e as
  credenciais do Educacenso protegem as coletas.
- O reinício após queda do servidor é responsabilidade de um script externo do
  operador (via journal); este repositório não gerencia serviço.

> **Confidencialidade:** em HTTP puro, as credenciais do Educacenso, as
> planilhas enviadas e os relatórios com PII trafegam **sem criptografia**.
> Firewall/VPN limitam quem conecta, mas não protegem contra observação do
> tráfego. Para acesso remoto, prefira `--server.address 127.0.0.1` + túnel SSH
> (ou VPN). Se houver certificado, o Streamlit aceita `--server.sslCertFile` e
> `--server.sslKeyFile`.

> **Atenção (LGPD/rede):** sem autenticação própria, qualquer pessoa que
> alcançar a porta do servidor consegue abrir o HUB. Restrinja a porta à rede
> local/VPN, nunca a exponha diretamente à internet, e mantenha o firewall do
> host fechado para origens não autorizadas.

## 2. Pré-requisitos

- Linux no servidor local (o host onde o `uv` será executado).
- `git` e `uv` instalados. Para instalar o `uv`:

  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

- Python 3.14: o `uv` baixa a versão exigida pelo `pyproject.toml` no
  `uv sync` (não é necessário instalar manualmente).
- Bibliotecas de sistema do Chromium/Playwright. Instale uma única vez como o
  **usuário operador** (não rode `uv`/`uv sync` com `sudo`; o Playwright eleva
  apenas o `apt` quando necessário):
- Recomendado, usando o próprio Playwright:

  ```bash
  uv run playwright install --with-deps chromium
  ```

  Alternativa em Debian/Ubuntu (a lista está em `packages.txt`):

  ```bash
  sudo apt-get update
  sudo xargs -a packages.txt apt-get install -y
  uv run playwright install chromium
  ```

  Em outras distribuições, use `uv run playwright install-deps chromium`.
- Saída de rede para o portal do Educacenso (`acesso.inep.gov.br` e
  `www.educacenso.inep.gov.br`) e, na primeira instalação, para baixar
  dependências e o Chromium.

## 3. Primeira execução

Na raiz do projeto:

```bash
uv sync
uv run playwright install --with-deps chromium   # uma única vez no host
mkdir -p logs
uv run streamlit run app.py --server.port 8501
```

O Streamlit imprime as URLs (`Local URL` e `Network URL`). Em um servidor sem
interface gráfica o navegador não abre sozinho (`.streamlit/config.toml` define
`server.headless = true`); acesse pelo navegador de outra máquina.

Se o diretório `logs/` não existir ou não for gravável, o HUB continua no ar e
o log cai para o stderr do terminal (veja a seção 7).

## 4. Acesso e porta

- Por padrão o Streamlit escuta em todas as interfaces (`0.0.0.0`). Em host com
  mais de uma interface, limite ao IP da LAN:

  ```bash
  uv run streamlit run app.py --server.address <ip-da-lan> --server.port 8501
  ```

  e acesse `http://<ip-ou-nome-do-servidor>:8501/`.

- Para escolher outra porta na hora:

  ```bash
  uv run streamlit run app.py --server.port 8510
  ```

- Para permitir acesso **somente da própria máquina** (e usar um túnel SSH):

  ```bash
  uv run streamlit run app.py --server.address 127.0.0.1 --server.port 8501
  ```

- Libere a porta escolhida no firewall **apenas** para as origens autorizadas.
  Exemplo com UFW (ajuste `<CIDR-da-rede>`; **garanta a regra do SSH antes de
  habilitar**, senão você pode perder o acesso remoto):

  ```bash
  sudo ufw allow 22/tcp
  sudo ufw default deny incoming
  sudo ufw allow from <CIDR-da-rede> to any port 8501 proto tcp
  sudo ufw enable
  sudo ufw status verbose
  ```

  Em `firewalld`, use uma regra rica equivalente (porta 8501/tcp, origem
  restrita) e recarregue. Verifique de uma máquina **não autorizada** que
  `nc -vz <ip-do-servidor> 8501` falha; de uma autorizada,
  `curl http://<ip>:8501/_stcore/health` deve responder `ok`.

## 5. Parar e reiniciar

- Pare com `Ctrl+C` no terminal onde o Streamlit está rodando.
- Se o terminal for encerrado, o processo cai junto. Para janelas longas, rode
  em `tmux`/`screen` ou com `nohup`; mantenha a supervisão do seu script de
  reinício, mas **atualize o comando dele** para o novo modelo (seção 5.1) — um
  script antigo que sobe Docker/Caddy não serve.
- Para reiniciar depois de uma queda, repita o comando da seção 3 (não é
  preciso reinstalar dependências nem o Chromium).

### 5.1 Migração do modelo anterior (Docker/Caddy)

Se o servidor já rodava a stack antiga:

1. **Pare a stack antiga.** No checkout antigo, `docker compose down`. Se o
   `git pull` já removeu o compose, localize e pare os containers:
   `docker ps --format '{{.Names}}' | grep censoapp` → `docker stop <nomes>` →
   `docker rm <nomes>`. A imagem `censoapp:latest` pode ser removida
   (`docker image rm censoapp:latest`); os volumes `censoapp_caddy_data` e
   `censoapp_caddy_config` continham só a CA/certificados do Caddy e não são
   mais usados.
2. **Libere as portas.** Confirme que 80/443/8501 estão livres:
   `ss -ltnp | grep -E ':(80|443|8501)'`.
3. **Descarte a configuração antiga.** Remova `.env` (CENSO_DOMAIN/portas/
   CENSO_AUTH_MODE) e `.streamlit/secrets.toml` (senha/OIDC). O HUB novo não lê
   esses arquivos; não os recrie. Se a senha antiga era compartilhada, avise os
   usuários e rotacione o que for necessário.
4. **Atualize o script de reinício.** Mantenha a supervisão via journal, mas
   troque o comando para o `uv`, com diretório e usuário corretos:
   `WorkingDirectory=/caminho/censoapp`, `User=<operador>`,
   `ExecStart=/caminho/uv run streamlit run app.py --server.port 8501`.
   Rode `uv sync` como operador antes da primeira subida; não use `sudo`.
5. **Ajuste o firewall.** Feche 80/443 e libere a porta nova apenas para a rede
   autorizada (seção 4).
6. **Valide** com os critérios da seção 9.

## 6. Atualização

```bash
# pare o HUB (Ctrl+C)
git pull
uv sync
uv run streamlit run app.py --server.port 8501
```

`uv sync` respeita o `uv.lock` versionado. Se o `git pull` não trouxer mudanças
de dependências, o comando é rápido; não há build de imagem.

## 7. Logs, dados e privacidade

- Log do HUB: `./logs/censoapp.log`, rotativo (5 MB × 5 arquivos), configurado
  por `logging_setup.py`. Variáveis opcionais:
  - `CENSO_LOG_DIR` — diretório do log (padrão: `logs/` relativo ao diretório
    de execução);
  - `CENSO_LOG_LEVEL` — nível do logger (padrão: `INFO`).
- Se o diretório não puder ser gravado, o HUB **não cai**: o log vai para o
  stderr com um aviso. Corrija a permissão e reinicie.
- **Sem PII no log**: códigos INEP e mensagens técnicas; nunca nomes de
  alunos/gestores, CPF ou credenciais.
- Temporários de coleta ficam em `/tmp` (`educacenso_*_tmp_`) e são removidos
  ao final de cada execução.
- Relatórios de inconsistências com PII são memoizados **por sessão**; somente
  o agregado de cor/raça usa `st.cache_data` (`ttl=300`). Nada é persistido em
  disco pelo HUB.
- XLSX/ZIP gerados são baixados pelo navegador do usuário; o servidor não os
  arquiva.

## 8. Testes

Suíte offline (não depende de rede nem do HUB no ar):

```bash
uv run python -m pytest -q
uv run ruff check .
```

Auditoria HTTP opcional contra o HUB em execução (testes não intrusivos,
pulados por padrão). O alvo é obrigatório:

```bash
SECURITY_LIVE=1 SECURITY_TARGET=http://localhost:8501/ \
  uv run python -m pytest tests/security/
```

A auditoria cobre métodos HTTP e exposição de caminhos/arquivos sensíveis. Os
testes de TLS/HSTS e dos cabeçalhos fornecidos pelo Caddy foram removidos com o
proxy. O HUB **não envia** `X-Frame-Options`, CSP nem `nosniff`; a restrição de
rede é o controle compensatório e o HUB não deve ser embutido em iframe.

## 9. Critérios de aceite da execução

- [ ] `uv sync` conclui sem erro (Python 3.14 do `uv.lock`).
- [ ] `curl http://localhost:8501/_stcore/health` responde `ok`.
- [ ] O HUB abre direto na Tela Inicial, **sem tela de senha**.
- [ ] O menu lateral troca de página e o download da documentação em PDF funciona.
- [ ] `./logs/censoapp.log` recebe linhas (sem PII).
- [ ] Uma coleta de teste (1–2 escolas) roda com o Chromium do host.
- [ ] `uv run python -m pytest -q` e `uv run ruff check .` passam.
- [ ] A porta não responde de uma máquina/rede não autorizada (`nc -vz`).
- [ ] Na migração, não há containers `censoapp-*` antigos no ar (`docker ps`).
- [ ] (Opcional) auditoria `tests/security/` contra `http://localhost:<porta>/`.

## 10. Troubleshooting

| Sintoma | Causa provável | Ação |
|---|---|---|
| `uv: command not found` | `uv` não instalado ou fora do `PATH` | Instale (seção 2) e reabra o terminal; em geral fica em `~/.local/bin` |
| `uv sync` falha ao resolver Python | 3.14 indisponível/ rede bloqueada | `uv python install 3.14` e repita; confira a saída de rede |
| `Address already in use` | porta ocupada | Escolha outra `--server.port`; veja `ss -ltnp \| grep 8501` |
| Chromium não inicia / falta `.so` | bibliotecas de sistema ausentes | `uv run playwright install --with-deps chromium` (o Playwright eleva só o apt; não rode `uv` com sudo) |
| Chromium não baixa | rede bloqueada no servidor | Instale em máquina com internet e copie o cache do Playwright, ou libere o download |
| Download da coleta abre e fecha | processo/pasta temporária sem permissão | Confira `/tmp` e o usuário que roda o HUB; o log mostra o erro |
| Nada no log | diretório ausente/sem permissão | `mkdir -p logs`; `CENSO_LOG_DIR`; o HUB avisa no stderr |
| HUB cai ao fechar o terminal | processo em foreground | Use `tmux`/`screen`/`nohup` ou o script de reinício do operador |
| Outra máquina da rede não acessa | bind em `127.0.0.1` ou firewall | Use `--server.address 0.0.0.0`/IP da LAN e libere a porta para as origens certas |
| HUB antigo ainda pede senha / 80/443 respondem | stack Docker/Caddy antiga no ar | `docker ps`; pare/remova os containers e siga a seção 5.1 |
| `.venv` com dono root / erros de permissão | `uv`/`uv sync` executado com sudo | remova `.venv` e rode `uv sync` como o usuário operador |
| Perdeu o acesso remoto após ligar o UFW | regra do SSH não liberada | Acesse pelo console e ajuste `ufw allow 22/tcp` (seção 4) |
| Página em branco/WebSocket falha | rede/proxy intermediário | Acesse direto pelo IP:porta; não há proxy reverso nesta modalidade |
