# The ML bench's own image: a Python, the libraries it trains with at exact versions, and its two
# files. Nothing from the control plane (DEC-0011).
#
# Built from the repository root:  docker build -f workers/mlbench/Dockerfile -t taktus-worker-mlbench .
#
# The libraries are those requirements.txt pins, installed without resolving anything further,
# so that two builds of one tag train the same model from the same data and seed. The launch
# convention of the execution port applies: TAKTUS_UNIT_PORT and TAKTUS_UNIT_STATE_DIR are read
# by the worker as defaults; the state directory holds the checkpoints and the prepared data
# across jobs, so that a resumed training finds them in a new unit.

FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 \
    TAKTUS_UNIT_PORT=9000 TAKTUS_UNIT_STATE_DIR=/var/lib/taktus/unit
COPY workers/mlbench/requirements.txt /tmp/requirements.txt
RUN pip install --no-deps -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt \
    && groupadd --system unit && useradd --system --gid unit --home-dir /app unit \
    && mkdir -p /app /var/lib/taktus/unit && chown -R unit:unit /app /var/lib/taktus
COPY --chown=unit:unit workers/mlbench/worker.py workers/mlbench/bench.py /app/
USER unit
WORKDIR /app
VOLUME ["/var/lib/taktus/unit"]
EXPOSE 9000
CMD ["python3", "/app/worker.py", "--host", "0.0.0.0"]
