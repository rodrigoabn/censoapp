# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# HUB de Aplicações de Apoio — Censo Escolar (Streamlit + Playwright/Chromium)
# Build na intranet:  docker build -t censoapp .
# Uso normal via:     docker compose up -d        (ver docs/deploy.md)
# ---------------------------------------------------------------------------
FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Bibliotecas de sistema exigidas pelo Chromium (fonte: packages.txt)
COPY packages.txt /tmp/packages.txt
RUN apt-get update \
    && xargs -a /tmp/packages.txt apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* /tmp/packages.txt

# uv (mesmo gerenciador do desenvolvimento; o uv.lock fixa as versões)
# Pin aqui se quiser reprodutibilidade total do próprio uv, ex.: uv:0.12
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Dependências primeiro (camada cacheável; sem dev e sem instalar o projeto)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Chromium do Playwright já embutido: nenhum download em runtime.
RUN /app/.venv/bin/python -m playwright install chromium \
    && chmod -R a+rX /ms-playwright

# Código e assets (inclui os modelos apps/*/docs/modelo_coleta*.xlsx)
COPY . .

RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/logs \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["/app/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health')"]

CMD ["/app/.venv/bin/python", "-m", "streamlit", "run", "app.py", \
     "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
