---
id: UC-4.11
title: Error window and impact analysis
component: run
epic: E4
serves: [P6, P8, P12]
state: specified
version: 0.5.0
tests: []
adrs: {ADR-0014: 6611f7833deb, ADR-0021: 202e0442e7ec, ADR-0022: 69572977f46b}
supersedes: null
---

# UC-4.11 — Error window and impact analysis

## 1. What must be achieved

A result is suspect (UC-4.10), or a person reports that a result was wrong. Four questions follow:
since when, what else is affected, what was built on it, and what has left the system. Taktus
answers them over the provenance chain, without a person.

1. **Since when.** It walks back from the suspect result through its inputs to the source or the
   step that changed — a model version, a prompt version, an adapter version, a source whose
   digest changed, a process version. The first result produced after that change starts the
   window; the last one produced ends it. Where no change is found, the window starts at the
   earliest result the check would have marked, the check re-run over the recorded results.
2. **What is affected.** Every result inside the window from the same step, and every result
   derived from one of them: the chain read forward, across runs and across processes.
3. **What was built on it.** The affected results grouped by the process and step that read them,
   each with its exactness class — so that an `exact` result built on a `tolerant` one is visible
   as such.
4. **What has left the system.** For every affected result, whether an egress entry exists for it
   (ADR-0022 §4), of which kind, when, and through which connector or channel.

The output is the **impact analysis**: a structured object, one entry per affected result, with its
position in the window, its exactness class, what reads it, and whether it has left. It is the
first section of the incident (UC-6.8) and the input of the remediation plan (UC-4.12).

## 2. How it is verified

- A source changed midway through a series of runs: the window starts at the first run after the
  change and ends at the last; every derived result across two processes is listed; a result
  delivered through a channel is marked as having left.
- A result older than the provenance chain is reported as **unbounded**, which is itself a
  finding. Nothing that was not recorded is reconstructed.
- A window without a found cause is reported as such. A window is never guessed.
- The analysis changes nothing: no result, no record, no run.

## 3. Where the boundary lies

**Not detection.** Whether a result is suspect is UC-4.10. **Not repair.** What to do about the
affected results is UC-4.12. **Not inside a worker.** The chain names what a step read and when; it
cannot name what a worker read inside its own workspace beyond the inputs it was given (ADR-0021).
**Not before the record.** Runs from before the provenance chain existed cannot be bounded, and the
analysis says so.

## 4. What it rests on

The provenance chain with every input's time of reading and digest (ADR-0021 §3); the ledger's
egress entries (ADR-0022 §4); the process versions for the exactness classes (ADR-0014) and the
anchors downstream. Written first in `UC-4-result-defects.md` on 2026-09-17 with the provenance
chain, moved into this format in the migration's second step; the requirement is unchanged. No
version of the definition has this use case.
