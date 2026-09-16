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


class UnknownRun(RunError):
    pass
