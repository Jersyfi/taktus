# The Taktus image: one image, every role, selected at start by TAKTUS_ROLES (ADR-0002).
#
# Built from the repository root:  docker build -f deploy/docker/Dockerfile .
# The build stage installs the project into a virtual environment with uv, from the lock file,
# without the development tools. The runtime stage carries the checkout the environment points
# at — src/, the migrations, the contracts, the reference worker — and nothing else: no build
# tool, no compiler, no secret. Secrets reach the container as files (TAKTUS_*_FILE).

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
COPY contracts ./contracts
COPY migrations ./migrations
COPY workers/script ./workers/script
COPY examples ./examples
RUN uv sync --frozen --no-dev

FROM python:3.13-slim-bookworm AS runtime
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 TAKTUS_STATE_DIR=/var/lib/taktus
RUN groupadd --system taktus && useradd --system --gid taktus --home-dir /app taktus \
    && mkdir -p /var/lib/taktus && chown taktus:taktus /var/lib/taktus
WORKDIR /app
COPY --from=build --chown=taktus:taktus /app /app
USER taktus
VOLUME ["/var/lib/taktus"]
EXPOSE 8080
CMD ["taktusd"]
