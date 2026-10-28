# Recordings of the self-development bundles

Each recording says where it was taken, in its own `recording.json` (`"taken"`):

| Process | Taken | From |
|---|---|---|
| `p01-roadmap-control` | local | no run of P-01 on the instance yet |
| `p02-refinement` | instance | `run_30ad9fcaf2fb24e441ba` of `p02-refinement@5`, on #528, 2026-10-18 |
| `p03-implementation` | local | no run of the current version on the instance yet; taken of version 22 and relabelled 23, which adds only a role to every fallback to a person (ADR-0146) |
| `s07-change-in-dialogue` | local | S-07 is not installed on the instance yet |

`tests/rehearsal/test_replay.py` holds this table to the `taken` of each recording.

What makes each local recording one from the instance — one run on the instance, ended,
recorded as below:

| Process | The run that is needed |
|---|---|
| `p01-roadmap-control` | a finished run of `p01-roadmap-control@4`: its daily schedule starts one once that version is active on the instance |
| `p03-implementation` | a finished run of `p03-implementation@22`: an issue it implements to the end, its pull request opened |
| `s07-change-in-dialogue` | S-07 registered on the instance, at version 1, and one change asked in the owner's conversation that ends, applied or declined |

A local recording was taken on a developer's machine against the repository's fakes — the
repository service, the model endpoint, the coding agent. It proves the replay and the export
end to end, not that the bundle still leads where a run on the instance led. A recording from
the instance proves that.

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

1. Note the tenant the process runs in. The tool takes the process's run itself: of its highest
   version, ended — finished or escalated — and not a rehearsal, the newest. `--run <run id>`
   names one instead.
2. In a runner of the instance, which has the `taktus` package and its configuration, write the
   recording into an empty directory:

   ```
   python3 record_rehearsal.py --tenant <tenant> --process <process id> --out /tmp/<process id>
   ```

   It prints the run it took. Check that its version is the bundle's in `blueprints/`.

   The tool is `tools/record_rehearsal.py`. It reads the database from
   `TAKTUS_DATABASE_URL_FILE` and the object store from `$TAKTUS_STATE_DIR/objects`, as the
   runner does, and writes nothing else.
3. Copy the directory here in place of the local one, and run `make rehearse`.
4. Read the result files before committing them: they are what the repository service and the
   model answered, and they become public with the commit. The secret scan runs on them in CI.
   The tool replaces every identifier of a person a connector answered — an issue's author —
   by `a person`; check that none is left.

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
