"""What a step sends outside the engine, as a document, and its digests (ADR-0108).

One definition, used twice: by the export, which reconstructs what each step of a real run
sent, and by the replay, which receives what the step sends now. Both digest the same document
the same way, so a request matches its recording exactly when it is the same request.

- a connector call and a wait: the operation and its input;
- a model call: the system text, the prompt and the output limit;
- a worker step: the task — goal, acceptance, inputs, the commands before and after the work.
  The workspace, the frame and the limits are not part of it: they are the engine's and the
  configuration's, not what the step asks for.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from taktus.adapters.driven.replay.recording import Request
from taktus.ports.model import Prompt
from taktus.ports.worker import Task


def canonical(document: Any) -> bytes:
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def digest(document: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(document)).hexdigest()


def connector(operation: str, input: Mapping[str, Any]) -> dict[str, Any]:
    # Through JSON once, so that a tuple and a list read the same.
    return {"operation": operation, "input": json.loads(canonical(dict(input)))}


def model(prompt: Prompt) -> dict[str, Any]:
    return prompt.document()


def worker(task: Task) -> dict[str, Any]:
    return task.document()


def request(document: Mapping[str, Any]) -> Request:
    """The digest of the request, and one per part: a top-level field, and each field of a
    top-level object."""
    parts: dict[str, str] = {}
    for key, value in document.items():
        if isinstance(value, Mapping) and value:
            for inner, part in value.items():
                parts[f"{key}.{inner}"] = digest(part)
        else:
            parts[key] = digest(value)
    return Request(digest=digest(dict(document)), parts=parts)


def differing(recorded: Request, given: Request) -> list[str]:
    """The parts in which two requests differ, by name: changed, added or gone."""
    names = sorted(set(recorded.parts) | set(given.parts))
    return [name for name in names if recorded.parts.get(name) != given.parts.get(name)]
