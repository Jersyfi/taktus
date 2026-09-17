# The reference worker's own image: one file on a Python base, nothing from the control plane.
#
# Built from the repository root:  docker build -f workers/script/Dockerfile -t taktus-worker-script .
#
# A worker executes foreign code; that is its purpose and the reason execution is isolated at
# all. It therefore never ships inside the control plane image (DEC-0011): this image is what an
# execution adapter launches (docs/architecture/contracts.md, the execution port), and what the
# development compose file starts as a worker configured by endpoint. The launch convention of
# the execution port applies: TAKTUS_UNIT_PORT is where the unit listens, TAKTUS_UNIT_STATE_DIR
# where its checkpoints live across jobs; both are read by the worker as defaults.

FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    TAKTUS_UNIT_PORT=9000 TAKTUS_UNIT_STATE_DIR=/var/lib/taktus/unit
RUN groupadd --system unit && useradd --system --gid unit --home-dir /app unit \
    && mkdir -p /app /var/lib/taktus/unit && chown -R unit:unit /app /var/lib/taktus
COPY --chown=unit:unit workers/script/worker.py /app/worker.py
USER unit
WORKDIR /app
VOLUME ["/var/lib/taktus/unit"]
EXPOSE 9000
CMD ["python3", "/app/worker.py", "--host", "0.0.0.0"]
