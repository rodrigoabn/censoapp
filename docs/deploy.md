# Implantação na intranet — HUB de Aplicações de Apoio (Censo Escolar)

Runbook para publicar o HUB em infraestrutura própria (SEDUCT) com Docker,
proxy reverso com TLS e autenticação institucional. Substitui o uso da
instância pública no Streamlit Community Cloud (checklist de despublicação na
seção 9).

## 1. Arquitetura

```text
navegador ──https──► Caddy (TLS + cabeçalhos) ──http──► app Streamlit :8501
                                                          ├─ Playwright/Chromium (embutido na imagem)
                                                          ├─ ./logs          (volume: log rotativo)
                                                          └─ secrets.toml    (montado somente-leitura)
```

- `caddy` publica apenas 80/443 (ajustáveis) — é o único serviço exposto no host.
- `app` não publica porta; fica acessível só na rede interna do compose (`expose: 8501`).
- Estado durável: `./logs` (log) e o volume `caddy_data` (CA/certificados TLS).
- Firewall: entrada só em 80/443; saída do container `app` para o Educacenso
  (`acesso.inep.gov.br` / `www.educacenso.inep.gov.br`). A telemetria do
  Streamlit está desligada (`.streamlit/config.toml` → `gatherUsageStats = false`).

## 2. Pré-requisitos

- Docker Engine + `docker compose` (v2).
- **Saída para internet durante o build** (apt, PyPI e Chromium do Playwright).
  Em rede fechada: construa a imagem em uma máquina com internet e transporte
  com `docker save censoapp:latest | gzip > censoapp.tar.gz` /
  `docker load < censoapp.tar.gz`.
- DNS interno apontando o domínio (ex.: `censo.seduct.intra`) para o servidor.
- Portas 80/443 livres (ou ajuste em `.env`).

## 3. Primeiro deploy

```bash
git clone <repo> censoapp && cd censoapp
cp .env.example .env                 # ajuste CENSO_DOMAIN, portas e CENSO_AUTH_MODE=oidc
mkdir -p logs                        # o app roda como uid 1000: logs/ aceita escrita
touch .streamlit/secrets.toml       # OBRIGATÓRIO antes do 1º up — ver gotcha abaixo
$EDITOR .streamlit/secrets.toml     # preencha [auth] (OIDC) ou [auth_simples] (senha)
docker compose up -d --build
docker compose ps                    # o serviço app deve chegar a "healthy"
curl -k https://localhost/_stcore/health   # "ok" (troque a porta se mudou no .env)
```

> **Gotcha (importante)**: o compose monta `./.streamlit/secrets.toml` como
> arquivo. Se ele **não existir** no primeiro `up`, o Docker cria um
> **diretório** no lugar e a aplicação quebra. Correção:
> `docker compose down && rmdir .streamlit/secrets.toml && touch .streamlit/secrets.toml`
> e suba de novo.

> **Permissões de `logs/`**: o app roda como uid 1000 (`appuser`). Crie o
> diretório no host com esse dono (`mkdir -p logs`; em Docker rootful com outro
> usuário: `sudo chown -R 1000:1000 logs`). Se o diretório não for gravável, o
> HUB **continua no ar** — o log cai para o stderr do container
> (`docker compose logs app`) com um aviso; corrija e reinicie.

O Caddy só inicia depois que o `app` fica `healthy` (`depends_on: service_healthy`).

## 4. Autenticação

O portão vive em `auth_gate.py` e roda no topo do `app.py`, **antes de qualquer
render**. O modo é detectado pela configuração e pode ser forçado com
`CENSO_AUTH_MODE` (valor inválido → erro explícito no start):

| Configuração            | Modo     | Uso                                   |
|-------------------------|----------|---------------------------------------|
| seção `[auth]`          | `oidc`   | **Produção** — SSO institucional      |
| seção `[auth_simples]`  | `senha`  | Fallback do MVP (senha compartilhada) |
| nenhuma das duas        | `aberto` | Somente uso local/dev (mostra aviso)  |

Se `CENSO_AUTH_MODE=oidc` for forçado sem `[auth]`, o HUB **fecha por padrão**
(tela de erro, nada renderiza). Não use `aberto` na intranet.

Recomendação: na intranet, fixe `CENSO_AUTH_MODE=oidc` no `.env` — assim uma
configuração faltante falha fechado em vez de cair no modo senha.

### 4.1 OIDC (recomendado)

Exemplo em `.streamlit/secrets.toml.example`. Para Google:

```toml
[auth]
redirect_uri = "https://censo.seduct.intra/oauth2callback"
cookie_secret = "<python -c \"import secrets; print(secrets.token_hex(32))\">"
client_id = "<client id>"
client_secret = "<client secret>"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

Para Keycloak interno, troque a última linha por:

```toml
server_metadata_url = "https://keycloak.seduct.intra/realms/<realm>/.well-known/openid-configuration"
```

- Registre o `redirect_uri` **exatamente** como está (HTTPS, caminho
  `/oauth2callback`) no provedor.
- Após editar secrets: `docker compose restart app`.
- Com o usuário logado, a sidebar mostra a identificação e o botão **Sair**.

### 4.2 Senha única (fallback)

```toml
[auth_simples]
senha = "<senha forte compartilhada>"
```

Comparação com `hmac.compare_digest`; “Sair” revoga a sessão. Use apenas
enquanto o OIDC não estiver disponível.

## 5. TLS e confiança da CA (Caddy `tls internal`)

Com `tls internal`, o Caddy gera uma CA própria. Para confiar no parque:

```bash
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt
# instale/distribua caddy-root.crt nos navegadores (ex.: GPO)
```

Alternativa com certificado corporativo real: monte o par
`cert.pem`/`key.pem` no serviço `caddy` e troque `tls internal` por
`tls /caminho/cert.pem /caminho/key.pem` em `deploy/Caddyfile`; nesse caso
habilite também a linha comentada de **HSTS** (só faça isso com certificado
confiável — HSTS com CA interna não distribuída é difícil de reverter).
Depois: `docker compose restart caddy`.

Para os **testes de segurança** a partir de um host com a CA instalada:

```bash
export REQUESTS_CA_BUNDLE=$PWD/caddy-root.crt
```

## 6. Cabeçalhos e CSP

O `deploy/Caddyfile` aplica: `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy` e uma
`Content-Security-Policy` compatível com o Streamlit (sem CDNs externas —
`default-src 'self'`).

Se alguma versão futura do Streamlit precisar de um recurso novo, o console do
navegador mostra `Refused to ...`; ajuste a diretiva no `Caddyfile` e rode
`docker compose restart caddy`.

## 7. Logs, dados e privacidade

- Log do HUB: `./logs/censoapp.log`, rotativo (5 MB × 5 arquivos), via
  `logging_setup.py`; no container `CENSO_LOG_DIR=/app/logs`.
- Se o diretório não puder ser gravado (ex.: `./logs` criado pelo Docker como
  root), o HUB **não cai**: o log vai para o stderr do container
  (`docker compose logs app`) com um aviso — corrija o dono do diretório.
- **Sem PII no log**: registrar códigos INEP e mensagens técnicas, nunca
  nomes de alunos/gestores, CPF ou credenciais.
- Temporários de coleta ficam em `/tmp` do container (`educacenso_*_tmp_`) e
  são removidos ao final de cada execução.
- Caches (`st.cache_data`) ficam **só em RAM**: os relatórios da verificação
  usam `max_entries=12` e o PDF da documentação é chaveado pela logo (entrada
  única). Nada é persistido em disco.
- XLSX/ZIP gerados são baixados pelo navegador do usuário; o servidor não os
  arquiva.

## 8. Atualização

```bash
git pull
docker compose up -d --build
docker compose ps          # app "healthy"
docker image prune -f      # ocasional: remove imagens antigas
```

O Caddy permanece no ar durante a recriação do `app` (os dados de TLS ficam no
volume `caddy_data`; não o remova, senão a CA muda).

## 9. Despublicação do Streamlit Cloud (obrigatória)

Enquanto a instância pública existir, o acesso continua possível sem o SSO.

1. Acesse <https://share.streamlit.io>, abra o app `censoescolar` → menu (⋮) →
   **Settings** → **Delete app** (ou remova o compartilhamento público).
2. Revise os *secrets* da instância Cloud (apague os que não forem mais usar).
3. Atualize referências à URL antiga (README, PDF de documentação, e-mails).
4. Daqui em diante, o alvo dos testes de segurança é o **interno**:

```bash
SECURITY_LIVE=1 SECURITY_TARGET=https://censo.seduct.intra/ \
  uv run python -m pytest tests/security/
```

(O default `censoescolar.streamlit.app` no `tests/security/conftest.py` fica
apenas como legado.)

## 10. Critérios de aceite da implantação

- [ ] `docker compose ps` → `app` **healthy** e `caddy` **running**
- [ ] `curl -k https://<dominio>/_stcore/health` → `ok`
- [ ] Cabeçalhos de segurança presentes (`curl -k -D - -o /dev/null https://<dominio>/`)
- [ ] Sem secrets → aviso de modo local; com `[auth]`: login institucional e
      “Sair” funcionam; com `CENSO_AUTH_MODE=oidc` sem `[auth]`: HUB fecha
- [ ] `./logs/censoapp.log` recebe linhas (sem PII)
- [ ] Coleta de teste (1–2 escolas) roda com o Chromium do container
- [ ] `SECURITY_LIVE=1 SECURITY_TARGET=https://<interno>/ uv run python -m pytest tests/security/`

## 11. Troubleshooting

| Sintoma | Causa provável | Ação |
|---|---|---|
| App quebra com `IsADirectoryError`/secrets | Docker criou diretório no lugar do `secrets.toml` | Seção 3 (gotcha): `down` → `rmdir` → `touch` → `up` |
| Caddy responde 502 | `app` ainda subindo ou `unhealthy` | `docker compose logs app`; aguarde o `start_period` |
| Porta 80/443 ocupada | outro serviço no host | `.env`: `CADDY_HTTP_PORT`/`CADDY_HTTPS_PORT` |
| Chromium não inicia no container | kernel/sandbox do host | já roda como não-root; se ainda falhar, adicione `security_opt: ["seccomp=unconfined"]` ao serviço `app` (último recurso) e registre a mudança; `shm_size: "1gb"` ajuda em coletas grandes |
| Página branca + erros `Refused to ...` no console | CSP bloqueou recurso novo | Ajuste a `Content-Security-Policy` em `deploy/Caddyfile` + `restart caddy` (seção 6) |
| Nada no log | diretório/volume | `docker compose exec app ls /app/logs`; confira `CENSO_LOG_DIR` |
| Aviso "Não foi possível gravar ..." e log só no stderr | `logs/` criado pelo Docker como root ou uid divergente | `sudo chown -R 1000:1000 logs` no host e `docker compose restart app` (o HUB segue no ar) |
| `StreamlitMissingAuthlibError` ao clicar em "Entrar" (modo oidc) | imagem antiga sem a dependência `authlib` | `docker compose up -d --build` (authlib consta no `pyproject`/`uv.lock`) |
| Navegador não confia no certificado | CA do Caddy não distribuída | Seção 5 (instalar `root.crt` ou usar certificado corporativo) |
