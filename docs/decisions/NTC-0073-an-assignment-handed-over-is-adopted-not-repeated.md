# NTC-0073 — An assignment handed over is adopted

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-09
**Raised in:** [#140](https://github.com/Jersyfi/taktus/pull/140), for issue #130

## 1. What was decided

A worker step hands its work to a worker as an *assignment*, with an id the run chooses.

- **Old:** the id reached the database only with `step.started`, after the worker had accepted
  the assignment. A runner that died in between left an assignment the ledger never named. A
  runner that died while the step ran left the assignment running in the worker. Either way the
  runner that recovered the run handed over a new assignment beside the old one. A runner that
  lost its claim asked the worker to stop its assignment.
- **New:** the id is committed first, with a `step.assigned` entry, and stays *open* in the step
  run until the step reads the assignment's end (ADR-0038). A step with an open assignment asks
  the worker about it before it hands over another:
  - an assignment the worker holds is *adopted* — `step.adopted`, and the stream is read on after
    the last event the step run holds;
  - one the worker does not know is posted again under the same id, so that a late post of a
    cut-off runner meets the worker's `409` and only one assignment runs;
  - a worker that cannot be asked fails the step, and nothing new is handed over.
- A runner that loses its claim leaves the assignment running for the runner that holds the
  claim now. An adopted assignment that ends stopped at a request the adopting runner did not
  make continues from its checkpoint with a new assignment. A stream that breaks off asks the
  worker to stop the assignment and leaves it open, so that a resume adopts what remains.

## 2. The evidence

- `tests/components/run/test_handover.py`: a crash after the worker accepted and before
  `step.started`, and a crash after the first inner boundary, each end with one assignment, every
  output once and the consumption counted once; an assignment that never reached the worker is
  posted again under its id; a late post of the same id makes the recovering post adopt it; an
  unreachable worker fails the step and a later resume adopts; an adopted assignment stopped by
  the dead runner continues; a broken stream asks for a stop and a resume adopts the rest.
- `tests/integration/test_handover.py`: two instances on PostgreSQL and the reference worker
  over HTTP; runner A stops after the worker accepted, after the first boundary, or before its
  post arrives. In each case the ledger names every assignment the worker accepted, every
  accepted assignment was continued to its end, no stop was needed, and the worker accepted one
  assignment for the step.
- `tests/integration/test_runner_failover.py` and `test_restart.py` kill a runner process with
  SIGKILL while the worker step runs; the step is adopted and not started again.

## 3. What was considered

- **Stop the orphaned assignment and hand over a new one from its checkpoint.** It needs no
  adoption. It throws away what the worker did after its last persisted boundary, and must
  wait for the stop before the new assignment starts. Adoption loses nothing.
- **Commit `step.started` before the post.** It would record a start the worker may refuse
  (NTC-0046).
- **A fresh id after a 404.** A cut-off runner's late post would then be accepted beside the
  recovering runner's.
- **A new contract operation listing a worker's assignments.** v1's state, stop, stream resume,
  404 and 409 already suffice; no contract changes.

## 4. Which entry permits it

M2.4: "A change of what the software does, made inside an agreed scope, that breaks no contract,
moves no limit or autonomy level and says nothing public." The scope is issue #130 in `0.2.0`.
The engine uses operations worker contract v1 already defines — the state of an assignment, its
`404` and its `409`, the resumable stream — and no contract under `contracts/` changes. No budget,
margin or level moves: an adopted step keeps the reservation it was admitted with.
