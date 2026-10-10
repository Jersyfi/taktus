# The Taktus image: one image, every role, selected at start by TAKTUS_ROLES (ADR-0002).
#
# Built from the repository root:  docker build -f deploy/docker/Dockerfile .
# The build stage installs the project into a virtual environment with uv, from the lock file,
# without the development tools. The runtime stage carries the checkout the environment points
# at — src/, the migrations, the contracts, the examples — and nothing else: no build tool, no
# compiler, no secret, and no worker. A worker executes foreign code; the control plane image
# contains none of it, so that a compromised control plane finds no execution primitive ready
# to hand (DEC-0011). Workers have their own images (workers/*/Dockerfile) and are reached
# through the execution port. tests/architecture holds this file to that.
# Secrets reach the container as files (TAKTUS_*_FILE).
# The web app is built in a stage of its own, from its lock file, and only its static build is
# carried over: the runtime image holds no Node and no package of the web app's (ADR-0063). The
# `api` role serves it under `{prefix}/app/`.

FROM node:24-bookworm-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
COPY contracts ./contracts
COPY migrations ./migrations
COPY examples ./examples
RUN uv sync --frozen --no-dev

FROM python:3.13-slim-bookworm AS runtime
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 TAKTUS_STATE_DIR=/var/lib/taktus
# The user is pinned by number, 999: the chart runs the image as that number under runAsNonRoot
# (deploy/k8s/chart/values.yaml, securityContext), and it must own what the image owns.
RUN groupadd --system --gid 999 taktus \
    && useradd --system --uid 999 --gid taktus --home-dir /app taktus \
    && mkdir -p /var/lib/taktus && chown taktus:taktus /var/lib/taktus
WORKDIR /app
COPY --from=build --chown=taktus:taktus /app /app
COPY --from=web --chown=taktus:taktus /web/build /app/web/build
USER taktus
VOLUME ["/var/lib/taktus"]
EXPOSE 8080
CMD ["taktusd"]
