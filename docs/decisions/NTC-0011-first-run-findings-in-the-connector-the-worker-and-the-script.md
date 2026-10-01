# NTC-0011 — The connector, the worker and first_run.sh

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-09-30
**Raised in:** [#51](https://github.com/Jersyfi/taktus/pull/51)

## 1. What was decided

- **The coding worker's changeset** carries `executable: true` for a file the index records as
  executable; `repository.branches.create` writes it so, and an explicit `false` wins over the
  base (issue #28).
- **The reference connector** gains `repository.files.read {path, ref}`, which names the commit it
  read at (issue #34).
- **P-03** gains a required input, `closing_section`, which its template appends after the
  worker's summary; the worker is told to leave that section out (issue #34; DEC-0037 for where
  an automatic start takes it from).
- **`tools/first_run.sh`** runs one bundle alone (`--only`, `--from`), resumes a stopped run
  (`--resume`), treats P-02's refusal of an issue whose criteria exist as done, and stops before
  anything starts when a branch of an earlier attempt exists, naming the two ways on; it never
  deletes a branch (issue #30).
- **The coding worker's token accounting** counts a message's tokens once it has seen the whole
  message (DEC-0038), and both reference workers halt at a boundary before crossing their limits
  (W-14).

## 2. The evidence

`docs/runs/first-run.md` §3–§5: seven attempts started by hand and seven branches deleted by hand
(#30); four refused descriptions on fixed text asked of the model, $3.48 of coding-step money
(#34); a new executable that would arrive plain (#28, not yet met). The tests:
`tests/adapters/connectors/test_repository_actions.py`, `tests/workers/test_coding_worker_changeset.py`,
`tests/tools/test_first_run.py`, `tests/integration/test_dev_orchestration.py`,
`tests/conformance`.

## 3. What was considered

- A committed copy of the generated section read with the new operation: rejected, it reverses
  part of DEC-0026.
- Deleting a leftover branch in the script: rejected, nothing deletes without asking.

## 4. Which entry permits it

M2.4: changes of what the software does inside the agreed scope of the first run's findings,
each additive to its contract, moving no limit or level and saying nothing public.
