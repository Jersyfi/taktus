# NTC-0263 — The response limit and the evaluations of support are parts of B-3.02, not processes of their own

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-11-04
**Raised in:** branch `concept/package-e--business` (package E, wave 2, concept mode, DEC-0222),
for issue #401
**How it follows:** UC-4.17 says a deadline "is declared in the process, beside its steps, and
kept by Taktus", so that no process keeps a timer of its own. UC-4.18 says a process's change
is held to *its* evaluation cases and its drift measured on the same cases. Both place what
UC-03 lists as B-3.12, B-4.01, B-4.02 and B-4.04 inside the process whose cases they are:
B-3.02. ADR-0142 §4 already placed B-4.06, the independent check, inside it. Of the two options
consistent with the sources, a bundle of its own per row would duplicate the timer and the
cases the use cases put in one place; the stricter in substance and the one with less ceremony
is to declare them in B-3.02.

## 1. What was decided

Version 2 of B-3.02 (`blueprints/software-operations/processes/B-3.02-draft-reply.yaml`)
declares:

- **B-3.12** as its deadline `first_answer`: eight working hours from the run to the step
  `send`, a reminder at six, an escalation to the role at the limit;
- **B-4.01, B-4.02 and B-4.04** as its `evaluation`: a rule scorer and a judge on `draft`, a
  weekly schedule for drift, and a set that starts empty and grows from corrected drafts a
  person confirmed.

B-4.03, the correction rate, is counted for B-3.02 per process and action by UC-7.5 without a
declaration. None of the five rows has a bundle of its own.

## 2. The evidence

- `tests/composition/test_software_operations.py` runs the shipped version: a case unanswered
  past its limit is reminded and escalated once, an answered one not; a corrected draft is
  proposed as a case, confirmed, run every week as a rehearsal that sends nothing, and a changed
  model behind the same name is a drift and an incident.
- The shipped `stages.yaml` names `b-3-12`, `b-4-01`, `b-4-02`, `b-4-04` and `b-4-06` in stage 2.
  A stage opens only once every process it adds runs (ADR-0191 §1). The blueprint's README
  therefore says that a tenant's plan names `b-3-02` for them.

## 3. What was considered

- **A bundle per row.** Rejected: B-3.12 would be a second run per message keeping a timer for
  the first, which UC-4.17 exists to prevent; B-4.01 to B-4.04 would need the cases of B-3.02,
  which UC-4.18 keeps with B-3.02.
- **Removing the rows from `stages.yaml`.** Rejected: the blueprint's stages list every process
  of UC-03 §4, and a test holds them to it. Which processes a stage adds stays the tenant's
  (UC-9.6 §3).

## 4. Which entry permits it

M2.6: no entry of `docs/decisions/anchors.taktus.md` covers where a row of a blueprint's
catalogue is served. The owner may overrule it in the pull request.

## 5. The entry it proposes

**M2.13** — *A row of a blueprint's catalogue that a use case places inside another process —
a deadline, an evaluation, a check — is declared in that process's bundle, and the blueprint's
README names the bundle that serves it.*
