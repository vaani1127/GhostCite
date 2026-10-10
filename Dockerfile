# GhostCite web UI in a small, non-root container.
#
#   docker compose up --build        # see compose.yaml: published on 127.0.0.1 only
#
# The API key is never part of the image: compose passes it from .env at run time
# (.dockerignore keeps .env out of the build context).

FROM python:3.12-slim AS build
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY samples ./samples
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /dist .

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    GHOSTCITE_CACHE_DIR=/cache \
    GHOSTCITE_IN_CONTAINER=1
COPY --from=build /dist /dist
RUN pip install --no-cache-dir /dist/*.whl \
    && rm -rf /dist \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin ghostcite \
    && mkdir -p /cache \
    && chown ghostcite:ghostcite /cache
USER ghostcite
WORKDIR /home/ghostcite
VOLUME ["/cache"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/status' % os.environ.get('PORT', '8000'), timeout=4)"]
# 0.0.0.0 is container-internal: it is needed so Docker can publish the port, and
# compose.yaml publishes it on 127.0.0.1 only. GHOSTCITE_IN_CONTAINER=1 makes the CLI
# explain this instead of printing the remote-access warning. Hosting platforms such as
# Render set PORT; without it (docker compose) the server listens on 8000.
CMD ["sh", "-c", "exec ghostcite web --host 0.0.0.0 --port \"${PORT:-8000}\""]
