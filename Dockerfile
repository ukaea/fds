FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /fds
COPY uv.lock pyproject.toml /fds/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev --extra s3 --extra otel
COPY app /fds/app
COPY alembic /fds/alembic
COPY alembic.ini README.md /fds/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra s3 --extra otel

FROM python:3.14-slim-bookworm
WORKDIR /fds
RUN groupadd --system fds && useradd --system --gid fds --uid 1000 --no-create-home fds
# Ownership set by the copy rather than a later chown, which would write a
# second copy of the whole virtualenv into its own layer.
COPY --from=builder --chown=fds:fds /fds /fds
# Unbuffered so anything using print() reaches the log stream as it happens.
# Logging itself flushes per record, but print() would otherwise sit in a block
# buffer and be lost if the process died.
ENV PATH="/fds/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER fds
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
