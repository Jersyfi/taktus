"""Whether a reader may see a run: one predicate, for the stream and every representation.

Who may see what is the reporting component's (ADR-0029, UC-6.4). Every read of a
representation and the stream of changes ask this function, so that no path is wider than
another (ADR-0055 §5). The stream asks it for each change when the change is sent, with the
reader's roles as they are then.

Until the role-based views of UC-6.4 are built (`0.5.0`), the predicate holds the boundary that
exists: a reader sees the runs of the tenant their identity belongs to, and no other. It knows
no roles yet; it receives them, so that the views can narrow it without a second path.
"""

from __future__ import annotations

from taktus.components.reporting.domain.model.live import Reader, RunRef


def may_see(reader: Reader, run: RunRef) -> bool:
    return run.tenant == reader.tenant
