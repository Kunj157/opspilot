# The API and the worker: one image, two entrypoints (opspilot-api, opspilot-worker).
# Build from the repository root: docker build -f apps/api/Dockerfile .
FROM ghcr.io/astral-sh/uv:0.11-python3.12-trixie-slim@sha256:7b5a3c8f80fb965911cf8f0c6690b30b39f10f691fc1e52cd6cc44bc509c3aeb AS build
# The venv is built where it runs, so its scripts' shebangs stay valid.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_FROZEN=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /src
# The detectors live in the ML project; the API imports them for inference.
COPY ml/pyproject.toml ml/uv.lock ml/README.md ml/
COPY ml/opspilot_ml ml/opspilot_ml
COPY apps/api/pyproject.toml apps/api/uv.lock apps/api/
WORKDIR /src/apps/api
RUN uv sync --no-dev --no-install-project --no-editable
COPY apps/api/src src
RUN uv sync --no-dev --no-editable

FROM python:3.12-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin opspilot
COPY --from=build /app/.venv /app/.venv
# Writable paths are mounted (/tmp); the root filesystem can stay read-only.
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp API_HOST=0.0.0.0 API_PORT=8000 EMBEDDING_CACHE_DIR=/tmp/models
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=2s CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=1)"]
CMD ["opspilot-api"]
