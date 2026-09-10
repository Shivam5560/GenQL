# 3.12 rather than :latest deliberately — uv.lock is resolved for it and
# .python-version pins it, so a newer interpreter would build against a lock
# that was never solved for it. Every *service* container runs :latest.
FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-dev

COPY . .
RUN uv sync --locked --no-dev

EXPOSE 8000

CMD ["genql", "serve", "--host", "0.0.0.0", "--port", "8000"]
