# syntax=docker/dockerfile:1.7
# One image for api and worker; they differ only in command. Built from the repo root.

FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /bin/
WORKDIR /app

# Dependencies only: this layer is rebuilt when uv.lock changes, not on every code edit.
FROM base AS deps
COPY pyproject.toml uv.lock .python-version ./
COPY packages/simcore/pyproject.toml packages/simcore/
COPY apps/api/pyproject.toml apps/api/
COPY apps/worker/pyproject.toml apps/worker/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace

FROM deps AS runtime
COPY packages/simcore/src packages/simcore/src
COPY apps/api/src apps/api/src
COPY apps/worker/src apps/worker/src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

ARG GIT_SHA=dev
ENV PATH="/app/.venv/bin:$PATH" \
    APOGEE_GIT_SHA=$GIT_SHA \
    APOGEE_DATA_DIR=/data
RUN useradd --create-home --uid 1000 apogee \
 && mkdir -p /data /cache /missions \
 && chown apogee /data /cache /missions
USER apogee

EXPOSE 8000
CMD ["uvicorn", "apogee_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
