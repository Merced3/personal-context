# Standalone container image for personal-context (context_substrate).
# For multi-repo ops builds, ops/docker/python-app.Dockerfile can also be used
# with ARG APP=personal-context.
FROM python:3.13-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml alembic.ini ./
COPY src ./src

RUN pip install --no-cache-dir .

ENV API_HOST=0.0.0.0 \
    API_PORT=8010 \
    HARNESS_DATA_DIR=/app/data/harness

EXPOSE 8010

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -fsS http://127.0.0.1:${API_PORT}/health || exit 1

CMD ["sh", "-c", "rm -f /app/data/harness/harness.lock && alembic upgrade head && exec python -m context_substrate"]
