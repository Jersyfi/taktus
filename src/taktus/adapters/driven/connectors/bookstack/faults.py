"""Fault injection: make the connector violate exactly one conformance check.

`--fault NAME` starts the connector with one of these. The conformance suite must then fail on
that check and on no other; `tests/conformance/test_connector_v1_knowledge.py` runs every fault
and holds the suite to it. The connector has no intake, so C-07 and C-08 have no fault: the
suite reports them as not applicable.

Every fault is applied in `server.py`, around the honest behaviour, so that `operations.py`
stays the honest implementation, with no switch in it.
"""

from __future__ import annotations

FAULTS: dict[str, str] = {
    "C-01": "the declaration omits knowledge.pages.read, which is still served as a tool",
    "C-02": "the result of the write claims effect read",
    "C-03": "a call without a credential is served with the value under KNOWLEDGE_TOKEN anyway",
    "C-04-result": "the credential value is copied into every result's output",
    "C-04-log": "the credential value is written to the log",
    "C-05": "the idempotency key is ignored: every write acts with a key of its own",
    "C-06": "an error is returned as bare text without the Error envelope",
    "C-09": "results report no consumption",
}


def check_of(fault: str) -> str:
    return fault[:4]


def validate(fault: str | None) -> frozenset[str]:
    if fault is None:
        return frozenset()
    if fault not in FAULTS:
        raise ValueError(f"unknown fault {fault!r}; known: {', '.join(FAULTS)}")
    return frozenset({fault})
