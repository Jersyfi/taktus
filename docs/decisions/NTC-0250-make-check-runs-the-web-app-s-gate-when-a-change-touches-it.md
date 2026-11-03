# NTC-0250 — `make check` runs the web app's gate when a change touches it

**Mode entry:** M2.2
**Kind:** test-strategy
**Decided:** 2026-10-30
**Raised in:** the session that installed rc.34, for the second run of P-03 on issue #335

## 1. What was decided

`make check` runs `make gate-web` — the web app's types, tests and build — when a change touches
a file under `web/`. A change that touches none prints that and costs nothing more.

## 2. The evidence

- Run `run_8ca217f4a55c57f98946` of `p03-implementation@23` built the web app's stage page for
  #335 and passed `make check` in its workspace.
- Its branch failed CI in the lane `web`: `svelte-check` found `seen[0]` possibly undefined in
  `web/src/lib/stages.test.ts`, and once that was typed, the test itself failed, because its
  stream ended before the reads it had asked for landed.
- P-03 asks its worker to run `make check` (P-03 v23, step `implement`). No lane of `make check`
  held the web app, so the worker could not have seen either failure.
- NTC-0243 closed the same kind of hole for the files `make generate` writes, after the first run
  on #335.

## 3. What was considered

- **Run `make gate-web` in every `make check`.** Rejected: `npm ci` and the build cost about a
  minute, and most changes touch no file of the web app.
- **Have P-03 run `make gate-web` itself.** Not instead: a person meets the same hole, and the
  check is where both stop before a commit.

## 4. Which entry permits it

M2.2: how a check is tested is the session's, and this one is made stricter, not weaker.
