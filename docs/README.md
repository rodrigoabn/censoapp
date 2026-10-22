# Documentação

## Para operar o HUB

- [`deploy.md`](deploy.md) — runbook: pré-requisitos, instalação, porta e
  firewall, logs, atualização e troubleshooting. É o documento a seguir para
  colocar o HUB no ar.

## Para desenvolver

- [`../AGENTS.md`](../AGENTS.md) — guia do projeto: arquitetura das 7 apps e
  dos 4 coletores headless, convenções de scraping, comandos de teste e o
  estado atual de cada tela.

## Histórico (arquivo)

Documentos das fases de construção do projeto, preservados como registro.
**Não são referência de uso** — o que está valendo hoje está no `AGENTS.md`
e no `deploy.md`.

- [`historico/plano_de_melhoria.md`](historico/plano_de_melhoria.md) — quadro
  das Fases 1 a 8 (hotfixes, intranet, testes golden, refatoração de
  `apps/common`, eficiência da coleta, régua fina, Coleta Automática e
  remoção das telas isoladas), com as decisões e o que ficou de fora.
- [`historico/superpowers/specs/`](historico/superpowers/specs/) — documento de
  design da aplicação Coleta Automática (o porquê de existir).
- [`historico/superpowers/plans/`](historico/superpowers/plans/) — planos de
  execução das duas últimas entregas (Coleta Automática e nova tentativa em
  timeout).
- [`historico/design/`](historico/design/) — rascunhos em HTML do brainstorm
  que precedeu a tela Coleta Automática, com o README explicando cada versão.
