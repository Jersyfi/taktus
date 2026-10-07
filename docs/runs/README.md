# Runs

What happened when Taktus was *used* rather than tested. One file per run worth a record —
not every run, only the ones that answered something: the first of a kind, the first that
failed in a new way, the first on a new platform.

A run record says what ran, what it consumed **against what was estimated**, where a person
had to step in, and what was slow, unclear or surprising. It is not a report to anybody: it is
the measurement the budget mechanism (ADR-0005) and the Takt (ADR-0010) are calibrated from,
and the list of frictions the next pull requests come out of. Every friction in it is an issue,
or it is not a friction anybody will fix.

| Record | What it is |
|---|---|
| [first-run.md](first-run.md) | 2026-09-23: the first time an issue of this repository became a pull request opened by Taktus. Four attempts, three defects, one flaky pipeline, and the first real numbers |
| [2026-09-19-the-run-that-stopped.md](2026-09-19-the-run-that-stopped.md) | 2026-09-19: the attempt before the credentials existed. P-02 ran to its language-model step and stopped; P-03 stopped at its admission check, correctly. Kept because its friction list is still the honest one |

**Why two files both about "the first run".** The record of 2026-09-19 was called the first run
when it was written, and it was the first time the bundles met the real repository. It was not a
run that finished. Rather than rewrite it — a record of what was known then is worth more than a
tidy one — it keeps its findings under the date it was written, and `first-run.md` is the run
that completed the criterion. The restructuring is NTC-0004.

## What the next live run must measure

**Read this before briefing the next live run.** Three mechanisms were built after the last live
run, on 2026-09-23, and have never run against a real service. Every test of them uses fakes. A
live run that does not measure them leaves them unproven for another round.

**Why they never ran live.** The budget (ADR-0005, third amendment), the rehearsal of the removal
test (ADR-0030) and admission against free capacity (ADR-0031) were built in #51, on 2026-09-30
and 2026-10-01, a week after the first run. No live run has happened since: `tools/first_run.sh`
is the only way to run one, it runs on the owner's machine with the owner's credentials, and the
platform the capacity half is meant for is not deployed yet. The one live call since was the
output-limit check M-03 against the model endpoint (NTC-0018).

**What the next run must measure, and where to read it.**

| Mechanism | What must be measured | Where the evidence is |
|---|---|---|
| the budget under the new margin (DEC-0034, DEC-0043) | per step: the estimate, the reservation and the actual. The coding worker's first reservation comes from its history in the ledger, else from the seed of the first run — its measured error, 1.8 to 4.3 times the estimate; each further observation narrows the margin by 1/(n+1), never below 10 %, and a changed model version starts it again at twice the estimate. Whether the actual stays inside the reservation is the question the margin was set to answer | `step.admitted`, `step.reserved` and `step.finished` in the run's ledger; `taktusctl cost <run>` for the money |
| a halt at a boundary on a real reservation | a second run of P-03 with its `limits` lowered below what the coding step used in the first — tokens, not money, so that the halt does not depend on the worker reporting money only at the end. The worker must halt at its next boundary (check W-14), the run must stop at the step boundary with the limit as its cause, and a resume with the old limits must continue from the checkpoint | the run's ledger; the worker's `assignment.finished.limit`; the resumed run's provenance chain without a gap |
| admission against real free capacity | on the deployed instance, the figures `taktusctl capacity` reports beside the node's own; a job admitted only when the unit's memory plus the reserve is free | `taktusctl capacity`; the ledger's `capacity.*` entries. This half waits for the deployment (NEED-0007) |
| the rehearsal | S-01 on an instance where a process with an outward write has run for real, so that the rehearsal answers from a real recording instead of resolving the process statically | `removal.tested` with outcome `rehearsed` steps and no egress entry. This waits for the deployment, because the weekly job starts from fresh state |

The record of the run goes into this folder like `first-run.md`, with the measurement of each row
above. A row it could not measure is named, with the reason.
