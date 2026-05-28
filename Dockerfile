FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-default-groups --no-install-project

COPY app/ ./app/
COPY core/ ./core/
COPY db/ ./db/
COPY cli/ ./cli/
COPY migrations/ ./migrations/
COPY alembic.ini main.py ./

ENTRYPOINT ["python", "-m", "cli"]
CMD ["--help"]
