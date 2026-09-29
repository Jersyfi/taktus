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
