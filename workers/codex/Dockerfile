# The second coding worker's own image: a Python for the worker, git for the workspace, the
# agent's command-line interface with the runtime its launcher needs, and two generic tools a
# task's command before the work prepares a workspace with: `uv`, a Python package manager, and
# `make` (ADR-0100). Nothing from the control plane (DEC-0011), nothing of the first coding
# worker, and nothing of one repository's toolchain: a repository installs its own linters and
# test runners with its command before the work (ADR-0092).
#
# Built from the repository root:  docker build -f workers/codex/Dockerfile -t taktus-worker-codex .
#
# The agent is installed from its package registry at build time, at the one exact version that
# workers/codex/agent-version names (README, "The agent's version"). A build whose file names
# anything but an exact version fails. The package's command is a small launcher that starts
# the native binary of the platform it was installed on; it runs on the registry image's own
# runtime, copied as its one binary.
#
# No credential is part of the image. Authentication is chosen at start (CODING_AGENT_AUTH) and
# the credential arrives at runtime under the name the assignment references, injected by the
# execution adapter. The launch convention of the execution port applies: TAKTUS_UNIT_PORT and
# TAKTUS_UNIT_STATE_DIR are read by the worker as defaults; the state directory holds the
# workspaces, the checkpoints and the agent's home across jobs.

FROM node:22-bookworm-slim AS agent
COPY workers/codex/agent-version /tmp/agent-version
RUN version="$(cat /tmp/agent-version)" \
    && printf '%s' "$version" | grep -Eqx '[0-9]+\.[0-9]+\.[0-9]+' \
    && npm install -g --fetch-timeout=30000 --fetch-retries=5 "@openai/codex@${version}" && npm cache clean --force

FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    TAKTUS_UNIT_PORT=9000 TAKTUS_UNIT_STATE_DIR=/var/lib/taktus/unit \
    CODING_AGENT_COMMAND=codex
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates make \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system unit \
    && useradd --system --gid unit --home-dir /home/unit --create-home unit \
    && mkdir -p /app /var/lib/taktus/unit && chown -R unit:unit /app /var/lib/taktus
# The agent's package with its platform's binary, as the registry ships them, and the runtime
# its launcher needs: its one binary, nothing else of the image it was installed from.
COPY --from=agent /usr/local/bin/node /usr/local/bin/node
COPY --from=agent /usr/local/lib/node_modules/@openai /opt/agent/@openai
RUN ln -s /opt/agent/@openai/codex/bin/codex.js /usr/local/bin/codex \
    && codex --version
# uv at one exact version: its two binaries and nothing else of its image.
COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /uvx /usr/local/bin/
COPY --chown=unit:unit workers/codex/worker.py /app/
USER unit
WORKDIR /app
VOLUME ["/var/lib/taktus/unit"]
EXPOSE 9000
CMD ["python3", "/app/worker.py", "--host", "0.0.0.0"]
