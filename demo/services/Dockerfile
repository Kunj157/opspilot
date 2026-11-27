# One image for all five demo services; SERVICE_NAME selects which one runs.
FROM ghcr.io/astral-sh/uv:0.11-python3.12-trixie-slim@sha256:7b5a3c8f80fb965911cf8f0c6690b30b39f10f691fc1e52cd6cc44bc509c3aeb AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin demo
COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PORT=8080
USER 10001
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=2s CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=1)"]
ENTRYPOINT ["opspilot-demo"]
