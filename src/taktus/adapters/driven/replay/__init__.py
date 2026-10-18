"""The replay of a recorded run (ADR-0108): a recording, and the pools that answer from it.

A recording is a directory of data (`recording.py`): the steps of one real run of a process,
each with the state it reached and, where it left the engine, how the outside answered it. The
pools (`answers.py`) offer a connector, a model and a worker that answer each step of a
rehearsal with that answer, when the step sends what the recorded step sent (`requests.py`),
and refuse it with a reason naming the step otherwise. Nothing here reaches anything outside
the process: no network, no secret, no file but the recording's.
"""

from taktus.adapters.driven.replay.answers import ReplayPools
from taktus.adapters.driven.replay.recording import (
    Answer,
    Observed,
    RecordedArtifact,
    Recording,
    Request,
    Step,
    UnreadableRecording,
    read,
    write,
)

__all__ = [
    "Answer",
    "Observed",
    "RecordedArtifact",
    "Recording",
    "ReplayPools",
    "Request",
    "Step",
    "UnreadableRecording",
    "read",
    "write",
]
