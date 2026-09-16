"""Method.json: the eight method kinds and their subsets."""

from __future__ import annotations

from enum import StrEnum


class Method(StrEnum):
    """The kind of method that produces a step's result (ADR-0004)."""

    RULE = "rule"
    STATISTICS = "statistics"
    ML = "ml"
    NEURAL = "neural"
    LLM = "llm"
    WORKER = "worker"
    HUMAN = "human"
    WAIT = "wait"


# The subsets of Method.json#/$defs. The binding test holds each to its schema definition.

VARIABLE: frozenset[Method] = frozenset({Method.LLM, Method.WORKER})
"""Methods whose result can differ between two runs with the same input; a step on one of these
carries a fallback."""

PINNED: frozenset[Method] = frozenset({Method.ML, Method.NEURAL})
"""Methods reproducible only at a pinned model version; a step on one of these names its model."""

PRODUCING: frozenset[Method] = frozenset(
    {Method.RULE, Method.STATISTICS, Method.ML, Method.NEURAL, Method.LLM, Method.WORKER}
)
"""Methods that produce a result and therefore carry an exactness class (ADR-0018)."""

NON_PRODUCING: frozenset[Method] = frozenset({Method.HUMAN, Method.WAIT})
"""Methods that produce no result and carry no exactness class (ADR-0018)."""

EXACT_ADMISSIBLE: frozenset[Method] = frozenset({Method.RULE, Method.STATISTICS})
"""The only methods that may produce the result of a step classed exact (ADR-0014)."""
