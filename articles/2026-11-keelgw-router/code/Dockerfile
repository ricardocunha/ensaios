# The router image: multilingual-e5-small on ONNX Runtime plus the four-Tier
# head, on CPU. Build context: this folder (code/).
#
#   docker build -t keelgw-router .                      # the service (the last stage)
#   docker build --target e2e -t keelgw-router-e2e .     # the e2e test runner
FROM python:3.12.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# The embedding model at its pinned revision, sha256-verified. Its own layer:
# downloaded again only when fetch_model.py's pins change.
FROM base AS model
COPY src/keelgw_router/fetch_model.py /src/fetch_model.py
RUN python /src/fetch_model.py /opt/router/model

# numpy, onnxruntime and tokenizers from uv.lock; not the dataset's API client.
FROM base AS deps
COPY --from=ghcr.io/astral-sh/uv:0.9.18 /uv /bin/uv
WORKDIR /src
COPY pyproject.toml uv.lock README.md ./
RUN UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never \
    uv sync --frozen --no-default-groups --no-install-project --no-cache --python /usr/local/bin/python

# The e2e runner: pytest and the tests, nothing of the model. It reaches the
# router over the compose network.
FROM base AS e2e
COPY --from=ghcr.io/astral-sh/uv:0.9.18 /uv /bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never \
    uv sync --frozen --no-default-groups --group dev --no-install-project --no-cache --python /usr/local/bin/python
COPY tests/ ./tests/
ENV PATH=/opt/venv/bin:$PATH
USER 65532:65532
ENTRYPOINT ["pytest", "-p", "no:cacheprovider", "-s", "-m", "e2e", "tests/e2e"]

# The service; the last stage, so a plain `docker build .` builds it.
FROM base AS runtime
COPY --from=deps /opt/venv /opt/venv
COPY --from=model /opt/router/model /opt/router/model
WORKDIR /app
COPY src/ ./src/
COPY model/head.json model/metrics.json ./model/
ENV PATH=/opt/venv/bin:$PATH PYTHONPATH=/app/src \
    ROUTER_MODEL_DIR=/opt/router/model ROUTER_HEAD=/app/model/head.json PORT=8080
# Start the service's own way once (model, head and a warm-up classification):
# an image that can't start fails here, not at runtime.
RUN python -c "from keelgw_router import server; classify, info = server.load(); print('router: starts;', info, classify('rename x'))"
EXPOSE 8080
USER 65532:65532
HEALTHCHECK --interval=5s --timeout=3s --start-period=30s --retries=12 \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('PORT', '8080')}/healthz\", timeout=2)"]
ENTRYPOINT ["python", "-m", "keelgw_router.server"]
