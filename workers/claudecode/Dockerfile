# The coding worker's own image: a Python for the worker, git for the workspace, and the
# agent's command-line interface. Nothing from the control plane (DEC-0011).
#
# Built from the repository root:  docker build -f workers/claudecode/Dockerfile -t taktus-worker-coding .
#
# The agent is installed from its package registry at build time, at the one exact version that
# workers/claudecode/agent-version names; the live test installs the same (README, "The agent's
# version"). A build whose file names anything but an exact version fails.
#
# No credential is part of the image. Authentication is chosen at start (CODING_AGENT_AUTH) and
# the credential arrives at runtime under the name the assignment references, injected by the
# execution adapter. The launch convention of the execution port applies: TAKTUS_UNIT_PORT and
# TAKTUS_UNIT_STATE_DIR are read by the worker as defaults; the state directory holds the
# workspaces, the checkpoints and the agent's sessions across jobs.

FROM node:22-bookworm-slim AS agent
COPY workers/claudecode/agent-version /tmp/agent-version
RUN version="$(cat /tmp/agent-version)" \
    && printf '%s' "$version" | grep -Eqx '[0-9]+\.[0-9]+\.[0-9]+' \
    && npm install -g "@anthropic-ai/claude-code@${version}" && npm cache clean --force

FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    TAKTUS_UNIT_PORT=9000 TAKTUS_UNIT_STATE_DIR=/var/lib/taktus/unit \
    CODING_AGENT_COMMAND=claude
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system unit \
    && useradd --system --gid unit --home-dir /home/unit --create-home unit \
    && mkdir -p /app /var/lib/taktus/unit && chown -R unit:unit /app /var/lib/taktus
# The agent's package, as its registry ships it — a self-contained binary — and nothing else
# of the image it was installed from.
COPY --from=agent /usr/local/lib/node_modules/@anthropic-ai /opt/agent/@anthropic-ai
RUN ln -s /opt/agent/@anthropic-ai/claude-code/bin/claude.exe /usr/local/bin/claude
COPY --chown=unit:unit workers/claudecode/worker.py /app/worker.py
USER unit
WORKDIR /app
VOLUME ["/var/lib/taktus/unit"]
EXPOSE 9000
CMD ["python3", "/app/worker.py", "--host", "0.0.0.0"]
