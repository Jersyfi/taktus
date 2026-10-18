# NTC-0213 — The replay of the self-development bundles is a lane of its own

**Mode entry:** M2.2
**Kind:** test-strategy
**Decided:** 2026-10-18
**Raised in:** the pull request for issue #393

## 1. What was decided

A new suite, `tests/rehearsal/`, replays P-01, P-02, P-03 and S-07 from recordings of real runs
against a PostgreSQL database (ADR-0108). It runs under its own target, `make rehearse`, as a
lane of CI of its own, `rehearse` (`tools/lanes.py`, ADR-0096 §3). A pull request runs it when
it touches a bundle under `blueprints/`, a recording, the export tool, a migration or any module
under `src/`. Every module under `src/` counts because the replay reaches the core through the
composition root, whose import graph holds nearly all of it. `tests/tools/test_lanes.py` holds
the lane to every module the replay imports. A push to `main` runs it unfiltered and never
cancels it. `make verify` runs it wherever CI would. `make test` leaves the directory out, so it
runs once, in its lane. The job is one of the jobs the required check `gates` needs.

A pull request that changes what a step sends records that process again in the same pull
request, from the repository's fakes, as ADR-0108 §8 says. `docs/process/next-task.md` §4 and
`tests/rehearsal/recordings/README.md` say the same.

The suite holds the replay to three deliberate breaks: a bundle that sends another body, a
recorded answer that leads elsewhere, and a missing answer. Each must turn the replay red,
naming its step. The mechanism under it is covered on every pull request that runs `test` by
`tests/components/run/test_replay.py` and `tests/tools/test_record_rehearsal.py`. The second
records a real run of a small process, writes its recording with the export tool and replays it.

A second, opt-in file, `tests/integration/test_rehearsal_recordings.py`, makes the local
recordings again from runs against the repository's fakes. It runs only with
`TAKTUS_RECORD_LOCAL` set, to `1` for every process or to a list of process identifiers, and
writes into the repository. `tests/README.md` says the same.

## 2. The evidence

- ADR-0096 §1 places the rehearsal of the self-development bundles in ring 3: every commit on
  `main`, never cancelled. With strict matching (ADR-0108 §2), a pull request that changes what
  a step sends — a version bump of P-03 is enough, because its claim comment names the
  version — would merge green and turn `main` red. A red `main` holds every merge (ADR-0096 §5,
  #391). Ring 1 must therefore run it too, where a change touches it.
- The replay needs no credential and reaches nothing outside, so a pull request may run it:
  CLAUDE.md §9 keeps only a test that needs a credential off a pull request.
- `make rehearse` took 6.5 s locally against a container database: nine tests, four replays and
  three breaks among them. The local generator took 25 s and wrote the four recordings;
  `.tools/bin/gitleaks dir tests/rehearsal` found no leak in them.

## 3. What was considered

- **Run it on `main` only.** The first version of this notice decided so, following the ring
  ADR-0096 names. Rejected: a change that alters a request would turn `main` red after its merge
  and hold every pull request behind it.
- **Run it in `make test`.** It would run on every pull request that touches anything under
  `tests/`, and twice where both lanes run. A lane of its own runs it once, and only where it
  can be affected.
- **Run the local generator in every CI run.** It would prove the export end to end against the
  fakes on every commit. Rejected: it starts the repository service, the connector, the model
  endpoint and the coding worker, and writes into the tree. The export is proven by the smaller
  test against the fakes of the ports.

## 4. Which entry permits it

M2.2: "A change of test strategy and what the tests now cover." A suite is added with its own
target, its own lane and its own job, and `make test` leaves it out. No gate is weakened:
nothing that ran before runs less. No limit, level or use case requirement changes, so no entry
of mode 3 or 4 applies.
