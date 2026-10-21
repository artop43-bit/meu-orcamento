FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv

WORKDIR /app

# Leitura de comprovante por foto (v1.3): OCR local, em português, sem serviço externo.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-por \
    && rm -rf /var/lib/apt/lists/*

# Dependências primeiro (sem as de desenvolvimento), para aproveitar o cache de camadas.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

# Roda sem privilégios de root.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

# Aplica as migrações pendentes e sobe a API.
# --proxy-headers: o IP real do visitante vem do Caddy (X-Forwarded-For). A API não é
# exposta para fora da rede do Docker, então só o Caddy consegue mandar esse cabeçalho.
# Um processo só: o limite de tentativas por IP fica em memória (com 2 processos ele
# dobraria). As rotas síncronas já rodam em paralelo num pool de threads.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
