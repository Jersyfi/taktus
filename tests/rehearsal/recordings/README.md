# Recordings of the self-development bundles

**These recordings are local, standing in until a recording from the instance replaces them.**
Each was taken from a run on a developer's machine against the repository's fakes — the
repository service, the model endpoint, the coding agent — and says so in its own
`recording.json` (`"taken": "local"`). They prove the replay and the export end to end. They do
not prove that the bundles still lead where a run on the instance led.

One directory per process, named by its identifier: `p01-roadmap-control`, `p02-refinement`,
`p03-implementation`, `s07-change-in-dialogue`. `tests/rehearsal/test_replay.py` replays each
with the bundle under `blueprints/` (`make rehearse`, ADR-0108).

## What a directory holds

- `recording.json`: the run as a replay needs it — the process and its version, the inputs, the
  budget and margin, where it ended, and per step the state it reached and, for a step that
  left the engine, how the outside answered. What a step sent is kept as digests only.
- `results/<step>.json`: the result of a connector call or a model call, as the run kept it.
- `artifacts/<step>/<artifact>`: what a worker step produced, byte for byte.

They are data, never code. They carry no secret value, and no person is named in them.

## Replacing a recording with one from the instance

1. Pick a run of the process on the instance that ended — finished or escalated — and is not a
   rehearsal. Note its tenant and its identifier.
2. In a runner of the instance, which has the `taktus` package and its configuration, write the
   recording into an empty directory:

   ```
   python3 record_rehearsal.py --tenant <tenant> --run <run id> --out /tmp/<process id>
   ```

   The tool is `tools/record_rehearsal.py`. It reads the database from
   `TAKTUS_DATABASE_URL_FILE` and the object store from `$TAKTUS_STATE_DIR/objects`, as the
   runner does, and writes nothing else.
3. Copy the directory here in place of the local one, and run `make rehearse`.
4. Read the result files before committing them: they are what the repository service and the
   model answered, and they become public with the commit. The secret scan runs on them in CI.

## When the replay is red

A change that alters what a step sends — an operation, its input, a prompt, a task, a step added
or removed — fails the replay at that step, naming the parts of the request that differ. That is
the replay working. CI's lane `rehearse` runs it on the pull request, and `make verify` runs it
before. The pull request then records that process again, in the same pull request, from the
repository's fakes:

```
TAKTUS_RECORD_LOCAL=<process id> uv run pytest tests/integration/test_rehearsal_recordings.py \
    --basetemp=/tmp/taktus-record
```

`TAKTUS_RECORD_LOCAL=1` records all four. This holds for a recording from the instance too: the
pull request replaces it with a local one, which says `"taken": "local"` again, and the process
stays local until the new version has run on the instance and that run is recorded as above
(ADR-0108 §8). The replay is never loosened to let a changed request pass.
