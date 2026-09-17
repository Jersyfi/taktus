"""Structured logging for the daemon: one JSON object per line on stderr, never a secret.

`structlog` renders every event; a `Secret` reaches the renderer as an object and is written
through its `repr`, which masks it, so a secret cannot appear in a line by being logged as a
value. The startup log lists the effective configuration through `Settings.effective()`, which
masks every secret itself and names its source instead. `tests/composition` proves both ends.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from taktus.composition.settings import Settings

LEVELS = {"debug": logging.DEBUG, "info": logging.INFO, "warning": logging.WARNING}


def processors() -> list[Any]:
    """The chain every event goes through, shared with the test that renders through it."""
    return [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(sort_keys=True),
    ]


def configure(level: str) -> None:
    numeric = LEVELS.get(level, logging.ERROR)
    structlog.configure(
        processors=processors(),
        wrapper_class=structlog.make_filtering_bound_logger(numeric),
        logger_factory=structlog.PrintLoggerFactory(sys.stderr),
        cache_logger_on_first_use=False,
    )
    # The standard library loggers of the HTTP server go to stderr at the same level, one line
    # each; access logging is off — a request log is not a run's record.
    logging.basicConfig(
        level=numeric, stream=sys.stderr, format="%(levelname)s %(name)s %(message)s"
    )
    logging.getLogger("uvicorn.access").disabled = True


def log_effective_configuration(settings: Settings) -> None:
    logger = structlog.get_logger("taktusd")
    logger.info("configuration", **{variable: value for variable, value in settings.effective()})
