# The connectors' images: one image per connector, each a stage of this file (ADR-0158).
#
# Built from the repository root, one connector at a time:
#   docker build -f connectors/Dockerfile --target github -t taktus-connector-github .
#
# A connector reaches a product outside Taktus with a credential the requesting identity owns.
# It is a separate deployable, as every worker is (DEC-0011): the control plane image carries no
# connector, and a connector's image carries nothing of the control plane — no src/, no
# migration, no database driver. Each image holds the shared serving library
# (taktus_connectors/serving.py), its own connector and nothing of another connector, so that
# adding or changing one connector changes neither the core image nor any other connector's.
# tests/architecture holds this file to that.
#
# The libraries are the lock file's: the build stage exports the `connectors` group of
# pyproject.toml from uv.lock with its hashes and installs exactly that, so that an image runs
# the versions the tests ran. The user is pinned by number, 999, as the control plane's is: the
# chart runs every connector under the same securityContext (deploy/k8s/chart/values.yaml).
# Secrets reach the container as files (TAKTUS_CREDENTIAL_<NAME>_FILE, CREDENTIALS.md).

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-emit-project --only-group connectors -o requirements.txt \
    && uv venv /opt/connector \
    && VIRTUAL_ENV=/opt/connector uv pip install --require-hashes -r requirements.txt

FROM python:3.13-slim-bookworm AS base
ENV PATH="/opt/connector/bin:$PATH" PYTHONPATH=/app PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN groupadd --system --gid 999 connector \
    && useradd --system --uid 999 --gid connector --home-dir /app connector \
    && mkdir -p /app/taktus_connectors
COPY --from=build /opt/connector /opt/connector
COPY connectors/taktus_connectors/__init__.py connectors/taktus_connectors/serving.py /app/taktus_connectors/
WORKDIR /app
USER connector
EXPOSE 9100

# --- one stage per connector: its directory, and its module as the entry point ---------------
# The chart and deploy/docker/connectors.py pass `--host 0.0.0.0 --port <port>` and the
# connector's own arguments; without them it listens on 0.0.0.0:9100.

FROM base AS accounting
COPY --chown=connector:connector connectors/taktus_connectors/accounting /app/taktus_connectors/accounting
ENTRYPOINT ["python", "-m", "taktus_connectors.accounting"]
CMD ["--host", "0.0.0.0", "--port", "9100"]

FROM base AS anthropic
COPY --chown=connector:connector connectors/taktus_connectors/anthropic /app/taktus_connectors/anthropic
ENTRYPOINT ["python", "-m", "taktus_connectors.anthropic"]
CMD ["--host", "0.0.0.0", "--port", "9100"]

FROM base AS aws
COPY --chown=connector:connector connectors/taktus_connectors/aws /app/taktus_connectors/aws
ENTRYPOINT ["python", "-m", "taktus_connectors.aws"]
CMD ["--host", "0.0.0.0", "--port", "9100"]

FROM base AS bookstack
COPY --chown=connector:connector connectors/taktus_connectors/bookstack /app/taktus_connectors/bookstack
ENTRYPOINT ["python", "-m", "taktus_connectors.bookstack"]
CMD ["--host", "0.0.0.0", "--port", "9100"]

FROM base AS einvoice
COPY --chown=connector:connector connectors/taktus_connectors/einvoice /app/taktus_connectors/einvoice
ENTRYPOINT ["python", "-m", "taktus_connectors.einvoice"]
CMD ["--host", "0.0.0.0", "--port", "9100"]

FROM base AS github
COPY --chown=connector:connector connectors/taktus_connectors/github /app/taktus_connectors/github
ENTRYPOINT ["python", "-m", "taktus_connectors.github"]
CMD ["--host", "0.0.0.0", "--port", "9100"]

FROM base AS httpcheck
COPY --chown=connector:connector connectors/taktus_connectors/httpcheck /app/taktus_connectors/httpcheck
ENTRYPOINT ["python", "-m", "taktus_connectors.httpcheck"]
CMD ["--host", "0.0.0.0", "--port", "9100"]

FROM base AS mail
COPY --chown=connector:connector connectors/taktus_connectors/mail /app/taktus_connectors/mail
ENTRYPOINT ["python", "-m", "taktus_connectors.mail"]
CMD ["--host", "0.0.0.0", "--port", "9100"]

FROM base AS openai
COPY --chown=connector:connector connectors/taktus_connectors/openai /app/taktus_connectors/openai
ENTRYPOINT ["python", "-m", "taktus_connectors.openai"]
CMD ["--host", "0.0.0.0", "--port", "9100"]

FROM base AS prometheus
COPY --chown=connector:connector connectors/taktus_connectors/prometheus /app/taktus_connectors/prometheus
ENTRYPOINT ["python", "-m", "taktus_connectors.prometheus"]
CMD ["--host", "0.0.0.0", "--port", "9100"]

FROM base AS sentry
COPY --chown=connector:connector connectors/taktus_connectors/sentry /app/taktus_connectors/sentry
ENTRYPOINT ["python", "-m", "taktus_connectors.sentry"]
CMD ["--host", "0.0.0.0", "--port", "9100"]

FROM base AS slack
COPY --chown=connector:connector connectors/taktus_connectors/slack /app/taktus_connectors/slack
ENTRYPOINT ["python", "-m", "taktus_connectors.slack"]
CMD ["--host", "0.0.0.0", "--port", "9100"]

FROM base AS stripe
COPY --chown=connector:connector connectors/taktus_connectors/stripe /app/taktus_connectors/stripe
ENTRYPOINT ["python", "-m", "taktus_connectors.stripe"]
CMD ["--host", "0.0.0.0", "--port", "9100"]

FROM base AS vendor
COPY --chown=connector:connector connectors/taktus_connectors/vendor /app/taktus_connectors/vendor
ENTRYPOINT ["python", "-m", "taktus_connectors.vendor"]
CMD ["--host", "0.0.0.0", "--port", "9100"]
