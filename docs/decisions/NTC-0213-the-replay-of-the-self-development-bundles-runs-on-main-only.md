# NTC-0213 — The replay of the self-development bundles runs on `main` only

**Mode entry:** M2.2
**Kind:** test-strategy
**Decided:** 2026-10-18
**Raised in:** the pull request for issue #393

## 1. What was decided

A new suite, `tests/rehearsal/`, replays P-01, P-02, P-03 and S-07 from recordings of real runs
against a PostgreSQL database (ADR-0108). It runs under its own target, `make rehearse`, and in
CI's job `rehearse` on every push to `main`. `make test` leaves the directory out, so no pull
request runs it in CI. A session that changes a bundle or the run engine runs it locally before
it pushes (`docs/process/next-task.md` §4). The job is one of the jobs the required check
`gates` needs; on a pull request it is skipped, which passes.

The suite holds the replay to three deliberate breaks: a bundle that sends another body, a
recorded answer that leads elsewhere, and a missing answer. Each must turn the replay red,
naming its step. The mechanism under it is covered on every pull request by
`tests/components/run/test_replay.py` and `tests/tools/test_record_rehearsal.py`. The second
records a real run of a small process, writes its recording with the export tool and replays it.

A second, opt-in file, `tests/integration/test_rehearsal_recordings.py`, makes the local
recordings again from runs against the repository's fakes. It runs only with
`TAKTUS_RECORD_LOCAL=1`, and writes into the repository. It is removed when the recordings from
the instance replace the local ones. `tests/README.md` says the same.

## 2. The evidence

- ADR-0096 §1 places the rehearsal of the self-development bundles in ring 3: every commit on
  `main`, never cancelled. Its §6 puts it in phase 3, for `0.4.0`. Issue #393 asks for a job on
  `main`.
- `make rehearse` took 6.1 s locally against a container database: nine tests, four replays and
  three breaks among them. Its cost to a pull request would be small. The placement follows
  the ring, not the cost.
- The local generator took 25 s and wrote the four recordings; `.tools/bin/gitleaks dir
  tests/rehearsal` found no leak in them.

## 3. What was considered

- **Run it in `make test` on every pull request too.** It would catch a broken bundle before
  the merge. Rejected for now: ADR-0096 and the brief of #393 place it on `main`, and running it
  on pull requests is a change of that ADR's rings, a decision of its own. A session runs it
  locally when it touches a bundle, which covers the case at no cost to CI.
- **Run the local generator in every CI run.** It would prove the export end to end against the
  fakes on every commit. Rejected: it starts the repository service, the connector, the model
  endpoint and the coding worker, and writes into the tree. The export is proven on every pull
  request by the smaller test against the fakes of the ports.

## 4. Which entry permits it

M2.2: "A change of test strategy and what the tests now cover." A suite is added with its own
target and its own job, and `make test` leaves it out. No gate is weakened: nothing that ran
before runs less. No limit, level or use case requirement changes, so no entry of mode 3 or 4
applies.
