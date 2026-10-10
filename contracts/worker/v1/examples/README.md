# Examples and conformance fixtures

`make gate-contracts` validates everything here against the schema. The conformance suite uses
the transcripts as fixtures for its stream rules (`make gate-conformance`).

## Layout

```
examples/<definition>/valid/<name>.json          validates against Worker.json#/$defs/<Definition>
examples/<definition>/invalid/<name>.json        must fail
examples/<definition>/invalid/W-NN-<name>.json   must fail, and is the fixture for conformance check W-NN
```

The directory name is the definition in kebab-case: `assignment-state` is `AssignmentState`.

## Transcripts

Ten of the eighteen checks concern a whole stream, not one object. Their fixtures use the
`Transcript` shape — the assignment, the estimate the worker gave for it, and every event in order —
and fail one of the stream rules in `src/taktus/conformance/rules.py`, which
`tests/conformance/test_worker_v1_fixtures.py` applies to every file here:

| Check | Rule on the transcript |
|---|---|
| W-03 | `seq` runs 1, 2, 3, … without a gap |
| W-04 | every step that started has a `consumption.reported` before the next step starts |
| W-05 | at least one `step.boundary`, unless the assignment was rejected |
| W-06 | after the last `step.boundary` no step starts; `stopped` carries that boundary's `checkpoint_ref` |
| W-07 | a `tool.called` outside `allowed_tools` has `refused: true` |
| W-10 | an estimate above `limits` yields a stream of exactly one event, `assignment.finished` with `rejected` |
| W-11 | no two `artifact.produced` share a digest or an `artifact_id` |
| W-13 | a `tool.called` whose `host` is outside `allowed_hosts` has `refused: true` |
| W-14 | no step starts once the reported running total of a limited quantity has reached its limit; `limit` in `assignment.finished` comes with `stopped`, names a kind the limits set, and the checkpoint is the last boundary's |
| W-18 | a succeeded assignment whose task names a command after the work carries the artifact it names, and no step starts after it |

`transcript/valid/` holds both proof cases of the README — a shell script with no AI at all and a
training run that holds a GPU and is stopped at an epoch boundary — plus a rejection, a resume,
a coding run halted at the boundary where its input tokens reached their limit, and a coding run
whose task names a command after the work.

## Capacity probes

W-15 concerns no stream either. Its fixtures use the `CapacityProbe` shape: the places the worker
declares, the states of the assignments the suite held, the answer to one more, and what a lookup
of that assignment returned. They fail the capacity rule in `src/taktus/conformance/rules.py`,
which `tests/conformance/test_worker_v1_fixtures.py` applies to every file here. A worker holding
all its places answers one more with `503` and a problem body, and records nothing of it. An
accepted one more is no violation when a held assignment had finished by then: the worker may
have had a free place (`valid/a-place-freed-before-the-answer.json`).

## Id probes

W-16 and W-17 concern an assignment's id, not a stream. Their fixtures use two shapes, and fail
the two id rules in `src/taktus/conformance/rules.py`, which
`tests/conformance/test_worker_v1_fixtures.py` applies to every file here:

| Directory | Shape | Rule |
|---|---|---|
| `unknown-id-probe/` | `UnknownIdProbe`: an id never posted, and the answer to its state | W-16: `404` with a problem body |
| `repeated-id-probe/` | `RepeatedIdProbe`: the state of an assignment held, the answer to its id posted again, and the state after | W-17: `409` with a problem body, and the state after still the first assignment's — the same `accepted_at`, a `last_seq` no lower, and a finished state unchanged |

## Placeholders

Identifiers, digests and paths are invented. Credential names are names only; no example carries a
value, and the one file that does (`W-08`) exists to fail.
