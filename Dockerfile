FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /fds
COPY uv.lock pyproject.toml /fds/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev --extra s3
COPY app /fds/app
COPY alembic /fds/alembic
COPY alembic.ini README.md /fds/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra s3

FROM python:3.14-slim-bookworm
WORKDIR /fds
COPY --from=builder /fds /fds
ENV PATH="/fds/.venv/bin:$PATH"
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
