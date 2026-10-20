"""Logging do HUB: arquivo rotativo em `CENSO_LOG_DIR` (sem PII).

- `CENSO_LOG_DIR`  — diretório do arquivo (default `logs/`, relativo ao cwd).
- `CENSO_LOG_LEVEL` — nível do logger raiz (default `INFO`).

Se o diretório não puder ser gravado (ex.: `./logs` sem permissão para o
usuário que roda o HUB), cai para um handler de stderr com aviso — o HUB nunca
deixa de subir por causa do log.

A função é idempotente de propósito: o script do Streamlit roda de novo a cada
interação (rerun), e cada execução chama `configurar_logging()` — o handler do
arquivo é criado uma única vez por processo.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

_ENV_DIR = "CENSO_LOG_DIR"
_ENV_NIVEL = "CENSO_LOG_LEVEL"

ARQUIVO = "censoapp.log"
FORMATO = "%(asctime)s %(levelname)s %(name)s %(message)s"
MAX_BYTES = 5_000_000
BACKUPS = 5

_MARCADOR = "_censoapp_handler"


def _nivel_do_env(env: dict) -> int:
    """Converte `CENSO_LOG_LEVEL` em nível do logging (nome desconhecido → INFO)."""
    nome = str(env.get(_ENV_NIVEL, "INFO")).upper()
    return getattr(logging, nome, logging.INFO)


def configurar_logging(log_dir=None, level=None, env=None) -> Path:
    """Liga o arquivo rotativo (`censoapp.log`) ao logger raiz; retorna o caminho.

    `log_dir` tem precedência sobre `CENSO_LOG_DIR`; `level` (int) sobre
    `CENSO_LOG_LEVEL`. Chamadas repetidas não duplicam handlers.
    """
    env = dict(os.environ) if env is None else env
    if log_dir is None:
        log_dir = env.get(_ENV_DIR, "logs")
    caminho = Path(log_dir) / ARQUIVO

    raiz = logging.getLogger()
    criado = False
    erro = None
    if not any(getattr(h, _MARCADOR, False) for h in raiz.handlers):
        try:
            caminho.parent.mkdir(parents=True, exist_ok=True)
            handler: logging.Handler = RotatingFileHandler(
                caminho,
                maxBytes=MAX_BYTES,
                backupCount=BACKUPS,
                encoding="utf-8",
            )
        except OSError as exc:
            # Ex.: ./logs sem permissão de escrita (ver docs/deploy.md).
            # O HUB não pode deixar de subir por causa do log: cai para o stderr.
            erro = exc
            handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(FORMATO))
        setattr(handler, _MARCADOR, True)
        raiz.addHandler(handler)
        criado = True

    raiz.setLevel(_nivel_do_env(env) if level is None else level)

    # Uma linha por processo (depois do setLevel, senão o INFO seria descartado).
    if criado and erro is not None:
        raiz.warning("Não foi possível gravar %s (%s); log indo para o stderr.", caminho, erro)
    elif criado:
        raiz.info("Log gravando em %s", caminho)

    return caminho
