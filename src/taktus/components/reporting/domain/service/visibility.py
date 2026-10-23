"""Whether a reader may see a run: one predicate, for the stream and every representation.

Who may see what is the reporting component's (ADR-0029, UC-6.4). Every read of a
representation and the stream of changes ask this function, so that no path is wider than
another (ADR-0055 §5). The stream asks it for each change when the change is sent, with the
reader's roles as they are then. The read API asks it for every run it would show (#186).
Every caller calls it as `visibility.may_see`, through this module, and never imports the
function by name: a path that held its own reference would no longer be the one predicate, and
`tests/adapters/rest/test_reads.py` replaces it here to show that every path follows.

Until the role-based views of UC-6.4 are built (`0.5.0`), the predicate holds the boundary that
exists: a reader sees the runs and the processes of the tenant their identity belongs to, and
no other. It knows no roles yet; it receives them, so that the views can narrow it without a
second path.
"""

from __future__ import annotations

from collections.abc import Collection

from taktus.components.reporting.domain.model.live import CountedRuns, ProcessRef, Reader, RunRef
from taktus.components.reporting.domain.model.trace import OWNER


def may_see(reader: Reader, run: RunRef) -> bool:
    return run.tenant == reader.tenant


def may_count(reader: Reader, runs: CountedRuns) -> bool:
    """Whether a reader may see the runs of one process version counted together, without each
    run being read (ADR-0094). It never says yes where `may_see` would say no for a run among
    them: until UC-6.4 both hold the tenant boundary. A view of UC-6.4 that tells the runs of one
    version apart changes this predicate with it, or a count would show what `may_see` hides."""
    return runs.tenant == reader.tenant


def may_see_process(reader: Reader, process: ProcessRef) -> bool:
    """Whether a reader may see a process: its graph, its autonomy statement, its versions.
    The runs of a process are asked of `may_see` one by one; a process a reader may see can
    still have runs the reader may not."""
    return process.tenant == reader.tenant


def may_see_trace(reader: Reader, run: RunRef, shared_with: Collection[str]) -> bool:
    """Whether a reader may see the trace inside a step of a run (ADR-0135 §4). Only where
    `may_see` lets them see the run: a share never widens what a role sees of runs. Then the
    reader holds the owner's role, or a role the trace is shared with. A trace is shared with a
    role and never with a person, so no identity opens it by its name."""
    if not may_see(reader, run):
        return False
    return OWNER in reader.roles or any(role in shared_with for role in reader.roles)
