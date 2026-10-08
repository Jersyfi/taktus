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
