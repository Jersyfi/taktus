# ADR-0096 — CI checks what changed before a merge, and everything after it

**Status:** accepted · from DEC-0194 · evidence `docs/research/2026-10-13-ci-review.md` · built in four phases (§6)

## Context
CI is the gate every change of this repository passes, whether a session or P-03 Implementation
made the change. Since 2026-10-11 one run takes 26–27 minutes. CI runs during 52 % of the time a
pull request is open, and 44 % of the pull requests' CI minutes re-check a branch only because it
was brought up to date with `main`. The documentation gates cost under 15 seconds. The time goes
to two suites that run one after the other in one job, to the catch-ups, and to running every
check on every change.

P-03 waits for the pipeline's verdict before it opens a pull request. On the first live run that
wait was 64 % of the run's wall clock (`docs/runs/first-run.md`). A slow CI therefore slows
Taktus's own development as much as a session's.

A replay of the last 100 merges (§2 of the research) found that no merge would have produced a
different and broken tree without the catch-up. 30 catch-ups resolved real conflicts, almost all
in four files that many pull requests extend by hand.

## Decision

### 1. Five rings
Every check runs where it costs least. What changed is checked before a merge. Everything is
checked after it, on every commit.

| Ring | When | What |
|---|---|---|
| 0 local | every commit; before *ready* | `make check`: lint, types, architecture, the documentation and register gates, the tests of the components touched. `make verify`: the selection CI would make, by the same code, leaving a stamp for the commit it verified |
| 1 pull request | when a pull request is ready | the always-on checks (secrets, register, description) and the lanes the change touches, in parallel; one aggregate required check |
| 2 merge | the merge | no catch-up with `main` except on a textual conflict; a guard holds every pull request while `main` is red |
| 3 `main` | every commit on `main`, never cancelled | everything, unfiltered, plus a rehearsal of the self-development bundles |
| 4 night, week, candidate | on a schedule; on a release candidate | what is heavy or needs an environment: a real cluster, backup and restore, an upgrade from the previous release, scale budgets, the removal test, live tests under their cap |

### 2. One aggregate required check
The required check keeps its name, `gates`. It needs every job of the run, passes when each one
passed or was skipped as not touched, and always reports. On a draft it reports under another
name, so that a draft never satisfies the ruleset. Every job carries a timeout of about three
times its slowest green run. A test in `tests/architecture` fails on a job without one.

### 3. Selection by path, then by component
A path filter assigns every tracked path to a lane: Python core, integration, conformance per
contract, web, contracts, migrations, deploy, documentation. A test fails on a path no filter
claims.

Inside the Python core, the components touched are read from the import graph that `import-linter`
already enforces. Their tests run, and so do those of every component that depends on them. A
change to the shared kernel, `contracts/`, `pyproject.toml`, `uv.lock` or CI itself selects
everything. Local and CI selection are one implementation.

### 4. A draft is verified locally
CI does not run on a draft. A session hook refuses `gh pr ready` unless `make verify` left a
stamp naming the pushed head. P-03 does the same in its own step: it pushes a draft, verifies,
then marks the pull request ready. A push to `taktus/**` still runs CI, because P-03 reads the
pipeline's verdict there. A pull request from such a branch does not run it a second time for
the same commit.

### 5. `main` stays green, and a red `main` is the first task
- **The ruleset no longer requires an up-to-date branch.** The owner switches this once the guard
  and the automaton exist.
- **The guard.** The required check's last step fails on a pull request while the newest run on
  `main` is red, unless the pull request reverts or names `Mends main: <sha>`.
- **The automaton after every CI run:**
  - it repeats a failed run once;
  - a run that turns green on the repeat is recorded in the flake register with the test and the date, and is never hidden;
  - a red `main` opens the issue "main is red", which `docs/process/next-task.md` takes before any other task;
  - a green `main` closes the issue.
- **Shared files are de-conflicted.** The indexes of `docs/decisions/README.md` and
  `docs/adr/README.md`, and the tree of `docs/architecture/project-structure.md`, are generated.
  The milestone sections of `docs/status.md` move to a file each. This applies DEC-0026 to the
  cases the replay found.
- **A quarantined test is a weakened gate.** It is a notice of kind `gate-weakened` with a date by
  which it is mended. It keeps running at night.

### 6. Four phases

| Phase | What | Where |
|---|---|---|
| 1 | parallel jobs under one aggregate, `pytest-xdist`, conformance per contract, concurrency, timeouts, no duplicate run on `taktus/**`, the flaky tests mended, the secret scan without false reds | now |
| 2 | path filters with the completeness test, `make check` and `make verify`, the draft hook, the guard, the automaton, the flake register, the shared files de-conflicted | now |
| 3 | the self-development rehearsal on `main` (needs a real recording, #75), selection by component, the nightly ring, the gate self-test | `0.4.0` |
| 4 | a migration lane (#330), a contract-compatibility lane before the contracts freeze, scale budgets and a fleet upgrade for operators | `0.5.0` to `2.0.0` |

### 7. A test of wall-clock time runs alone (issue #528)
A test that asserts a bound on time measures the machine as well as the code. The marker
`timing` names these tests (three files under `tests/integration/`: the ledger and the run
listing at 500 000 entries, and a launched process). They form the lane `timing`, selected by the
same paths as `test`, which leaves them out (`-m 'not timing'`).

- **In CI** the lane is a job of its own on its own runner, so nothing else runs beside it. A push
  to `main` runs it with every other lane (ring 3).
- **In `make verify`** it is the last lane, and runs under `tools/machine_lock.py` exclusive. Every
  other lane runs under the same lock shared. Several sessions that verify on one machine then
  meet in the timing lane one at a time, and never while another session is inside a lane.
- **The bound does not change.** Issue #321 requires what the reader of the ledger route waits
  for: the time of the request, through the HTTP interface, not the database's own execution
  time. Measuring the database alone would admit a route that spends its time elsewhere. The
  median of five stays, because it removes one slow read.

## Alternatives
- **Measure the database's execution time** (`EXPLAIN ANALYZE`). Rejected: it would measure less
  than the requirement states. Section 7 keeps the request.
- **A merge queue.** Rejected for now: a personal repository has none. The guard and the automaton
  give the same safety without one.
- **Keep `strict`.** Rejected: 44 % of the CI minutes, and the replay found no merge it saved.
- **Deploy on every merge, as the reference project does.** Rejected: Taktus never deploys itself
  (ADR-0013 D).
- **Let Taktus run its own CI.** Rejected: Taktus must stay repairable without Taktus (ADR-0013
  C). CI stays outside it.

## Consequences
- Every lane is a `make` target. A person can run any check locally (principle 6).
- A new worker adds a conformance lane of its own instead of lengthening a serial block.
- `main` can be red for the length of one run after a merge of two individually green changes.
  The guard stops further merges until it is mended.
- The flake register and the nightly ring are read: a nightly job red twice in a row for a
  reason of its environment is mended or removed with a notice.

## Where this promise ends
- Before a merge, CI checks the lanes a change touches, not every combination with what merged
  meanwhile. That is ring 3's job, and it finds a break after the merge, not before it.
- The selection by component is as good as the import graph. Code reached by a string — a plugin
  entry point, a subprocess, a template — is not in it. Its lane is selected by path, and ring 3
  covers the rest.
- The self-development rehearsal answers outward calls from recordings. It proves that the
  bundles and the engine still run. It does not prove that a provider or GitHub still answers as
  recorded; the monthly live tests and a release candidate's run on the instance do.
- The lock covers what `tools/verify.sh` runs. A command a person starts by hand, `make check`,
  or any program that is not a Taktus lane still runs beside the timing lane on a laptop, and can
  still push a read over its bound. The lock waits for at most 45 minutes, then runs without it
  and says so. In CI the runner is the whole machine.
- No figure in this ADR is a promise about wall time. The targets of DEC-0194 are measured
  after each phase and reported with the before and after, as definition of done 11 asks.
