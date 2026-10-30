"""Typed errors of the run domain."""

from __future__ import annotations


class RunError(Exception):
    pass


class IllegalTransition(RunError):
    def __init__(self, what: str, from_state: str, to_state: str) -> None:
        super().__init__(f"{what} cannot go from {from_state} to {to_state}")


class UnsupportedWork(RunError):
    """A step this version of the run component cannot execute, or work it cannot read."""

    def __init__(self, step_id: str, message: str) -> None:
        self.step_id = step_id
        super().__init__(f"step {step_id!r}: {message}")


class RuleFailed(RunError):
    """A rule evaluated and found its condition false, or could not evaluate."""


class NoWorker(RunError):
    def __init__(self, step_id: str, required: tuple[str, ...]) -> None:
        super().__init__(
            f"step {step_id!r}: no configured worker offers {', '.join(required) or 'nothing'}"
        )


class NoConnector(RunError):
    def __init__(self, step_id: str, capability: str) -> None:
        super().__init__(f"step {step_id!r}: no configured connector serves {capability!r}")


class UnknownRun(RunError):
    pass


class RunExists(RunError):
    """A run was to be created under an identifier a run already has. A trigger's firing
    derives its run's identifier, so this is the answer to the same firing a second time."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"run {run_id!r} exists already")


class ClaimLost(RunError):
    """A write of a run executed under a runner's claim was refused: another runner has
    claimed the run's job since. Nothing of the write landed, and the runner does nothing
    more for the run (#107)."""


class TakeoverRefused(RunError):
    """A take-over or a hand-back that cannot be done in the state the run is in: the step is
    not a running worker step, no runner holds the run, another take-over is asked or held, or
    the lease of the take-over has lapsed and a runner took the step back (ADR-0128). Nothing
    was written."""


class MessageRefused(RunError):
    """A person's message to a step that cannot be handed to it: the step is not a running
    worker step, no runner holds the run, a person holds it, or its worker declares no steering
    (ADR-0156 §7). The message names which. Nothing was written."""


class UnknownTakeover(RunError):
    """No step of the run is held under the take-over named (ADR-0128)."""
