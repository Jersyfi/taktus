"""What the evaluation platform connector declares about itself: the document served as the
resource `taktus://connector/v1/capabilities`, in the shape of
`Connector.json#/$defs/Capabilities`.

Three capabilities, each switched on by configuring it on its own (UC-5.8, ADR-0305):

- `evaluations.records`: an evaluation's cases, results and scores kept in the platform as a
  copy, `marked` by identifiers derived from the key; and the scores the platform holds for a
  run of a data set, read back.
- `prompts.versions`: a prompt of a process version mirrored as a version of a prompt in the
  platform, `marked` by the key's reference kept in the version's configuration.
- `observability.costs`: the cost the platform computed for traces, read.

Every request is one unit of quota; each demand is the most one call can make.
"""

from __future__ import annotations

from typing import Any

type Json = dict[str, Any]

CONTRACT = "connector/v1"
VERSION = "1.0.0"
EVALUATIONS = "evaluations.records"
PROMPTS = "prompts.versions"
COSTS = "observability.costs"
ACTIONS_CREDENTIAL = "EVALUATION_PLATFORM_KEYS"

MAX_ITEMS = 50
"""The most cases one copy of an evaluation carries."""
MAX_SCORES = 10
"""The most scores one case's result carries."""
MAX_TRACES = 20
"""The most traces one reading of costs or of a run's scores names."""
MAX_LOOKUP = 10
"""How many of a prompt's newest versions a mirror reads for its mark, at most."""

OPERATIONS: list[Json] = [
    {
        "name": f"{COSTS}.read",
        "demand": {"quota_units": MAX_TRACES},
        "capability": COSTS,
        "effect": "read",
        "summary": "For each trace of `traces` (at most 20), the total cost the platform "
        "computed for it, in US dollars as decimal text, with its latency in seconds; a trace "
        "the platform does not hold is named absent.",
    },
    {
        "name": f"{EVALUATIONS}.write",
        "demand": {"quota_units": 2 + 2 * MAX_ITEMS + MAX_ITEMS * MAX_SCORES},
        "capability": EVALUATIONS,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Copy an evaluation into the data set `dataset`, as the run `run`: every "
        "case of `items` (`id`, `input`, `expected`) as an item of the data set, and every "
        "result of `results` (`item`, `trace`, `scores` of `name`, `value`, `comment`) as an "
        "item of the run with its scores on the trace. Every identifier is derived from the "
        "key; a repeat finds the first score and writes nothing.",
    },
    {
        "name": f"{EVALUATIONS}.read",
        "demand": {"quota_units": 1 + MAX_TRACES},
        "capability": EVALUATIONS,
        "effect": "read",
        "summary": "The run `run` of the data set `dataset`: each of its items with its trace "
        "and the scores the platform holds on that trace, at most 20 traces; `complete` says "
        "whether every item was read.",
    },
    {
        "name": f"{PROMPTS}.mirror",
        "demand": {"quota_units": 2 + MAX_LOOKUP},
        "capability": PROMPTS,
        "effect": "write",
        "idempotency": "marked",
        "summary": "Mirror `text` as a new version of the text prompt `name`, its configuration "
        "naming `source` — the process version and step it comes from — and the key's "
        "reference; a repeat finds the reference among the newest versions and writes nothing. "
        "Answers the platform's version number.",
    },
]


def capabilities() -> Json:
    return {
        "contract": CONTRACT,
        "version": VERSION,
        "capabilities": [EVALUATIONS, COSTS, PROMPTS],
        "operations": [dict(op) for op in OPERATIONS],
        "credentials": [{"name": ACTIONS_CREDENTIAL, "purpose": "actions"}],
        "consumption": {"kinds": ["quota"], "unit": "requests", "window_seconds": 60},
        "permissions": "passthrough",
    }
