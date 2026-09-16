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

Seven of the twelve checks concern a whole stream, not one object. Their fixtures use the
`Transcript` shape — the assignment, the estimate the worker gave for it, and every event in order —
and fail one of the stream rules in `src/taktus/conformance/rules.py`, which
`tests/conformance/test_worker_v1_fixtures.py` applies to every file here:

| Check | Rule on the transcript |
|---|---|
| W-03 | `seq` runs 1, 2, 3, … without a gap |
| W-04 | every step that started has a `consumption.reported` before the next step starts |
| W-05 | at least one `step.boundary`, unless the assignment was rejected |
| W-06 | after the last `step.boundary` no step starts; `stopped` carries that boundary's `checkpoint_ref` |
| W-07 | a `tool.called` outside `allowed_tools` or matching `forbidden` has `refused: true` |
| W-10 | an estimate above `limits` yields a stream of exactly one event, `assignment.finished` with `rejected` |
| W-11 | no two `artifact.produced` share a digest or an `artifact_id` |

`transcript/valid/` holds both proof cases of the README — a shell script with no AI at all and a
training run that holds a GPU and is stopped at an epoch boundary — plus a rejection and a resume.

## Placeholders

Identifiers, digests and paths are invented. Credential names are names only; no example carries a
value, and the one file that does (`W-08`) exists to fail.
