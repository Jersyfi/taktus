# The browser worker's own image: a Python, its driver at the exact version requirements.txt
# names, the headless Chromium of that release, the reference worker's file and its own two.
# Nothing from the control plane (DEC-0011).
#
# Built from the repository root:  docker build -f workers/browser/Dockerfile -t taktus-worker-browser .
#
# A worker executes foreign content; a browser loads foreign pages and runs their scripts. That
# is why it is isolated at all and never ships inside the control plane image. The launch
# convention of the execution port applies: TAKTUS_UNIT_PORT is where the unit listens,
# TAKTUS_UNIT_STATE_DIR where its checkpoints live across jobs.

FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/browsers \
    TAKTUS_UNIT_PORT=9000 TAKTUS_UNIT_STATE_DIR=/var/lib/taktus/unit
COPY workers/browser/requirements.txt /tmp/requirements.txt
# The system libraries Chromium needs come with `--with-deps`, as root, before the user exists.
RUN pip install --no-deps -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt \
    && python -m playwright install --with-deps --only-shell chromium \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system unit && useradd --system --gid unit --home-dir /app unit \
    && mkdir -p /app /var/lib/taktus/unit && chown -R unit:unit /app /var/lib/taktus
COPY --chown=unit:unit workers/script/worker.py /app/script_worker.py
COPY --chown=unit:unit workers/browser/worker.py workers/browser/browse.py /app/
USER unit
WORKDIR /app
VOLUME ["/var/lib/taktus/unit"]
EXPOSE 9000
CMD ["python3", "/app/worker.py", "--host", "0.0.0.0"]
