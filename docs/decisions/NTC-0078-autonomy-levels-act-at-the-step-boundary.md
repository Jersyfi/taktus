# NTC-0078 — Autonomy levels act at the step boundary

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-09
**Raised in:** [#153](https://github.com/Jersyfi/taktus/pull/153), for issue #78

## 1. What was decided

Until now a run carried its autonomy level and nothing read it: a process at level 2 ran like one
at level 3. Now the run engine applies the level before every step starts (ADR-0039):

- **The level of a step** is the lowest of the process's level and the levels of the tool actions
  the step uses — the capabilities it requires, the connector operation it calls or waits on, and
  that operation's capability. The bundle sets action levels under `autonomy.actions`.
- **At level 2** every step waits in `waiting_human` until a person confirmed it. A confirmation
  holds for the step: a resume after a failure does not ask again, because a resume is a
  person's act already.
- **At level 1** a step that *acts* — one that hands work to a worker, or calls a connector
  operation declared outward, or one whose declaration cannot be read — is never executed. Its
  proposal is recorded and it waits until a person reports the act performed. Rules, reads, a
  model's text and waits are the analysis Taktus supplies at level 1, and they run.
- **A waiting step holds back only the steps that depend on it.** The others run on, and the run
  waits once nothing else can run.
- **A raise** is checked where a version is registered, against the history the replaced version
  names, and needs a person's approval given with the registration.

The new behaviour of the example: `examples/processes/six-times-seven.yaml` is at level 2, so each
of its steps now waits for a confirmation, as its statement says ("a person confirms it").

## 2. The evidence

- UC-7.1 §1 names the levels by the person's role: at level 1 the person "decides and executes;
  Taktus supplies analyses, proposals and estimates of effort"; at level 2 the person "confirms
  every step before it runs". Issue #78's verification repeats both.
- UC-7.1 §2 and issue #78: "finds that action waiting for approval (`waiting_human`) while the
  rest of the run continues". A run that halted at the first waiting step would not continue.
- `docs/architecture/control-plane.md` §5.2 already drew `waiting_human` as the state of a run
  with an open approval.
- ADR-0026 puts the statement on the version, so a raise is a new version and registration is the
  one place where a level can rise.

## 3. What was considered

- **At level 1, nothing runs.** Rejected: UC-7.1 has Taktus supply analyses at level 1, which
  means reading and computing; only the act stays with the person.
- **At level 1, a confirmation lets Taktus act.** Rejected: that is level 2.
- **A confirmation asked again after every resume.** Rejected: a resume is a person's act at the
  same boundary, and asking twice for the same step adds ceremony without a person learning more.
- **Halting the whole run at the first waiting step.** Rejected: the rest of the run would not
  continue, which UC-7.1 asks for.

## 4. Which entry permits it

M2.4, *"A change of what the software does, made inside an agreed scope, that breaks no published
contract, moves no limit or autonomy level and says nothing public."* The scope is issue #78,
which the owner's backlog made ready; the contract change is an addition of two optional fields
to a `v1` schema no released version uses (ADR-0019); no level of any process moves, since the
example keeps its level 2 and the levels of the project's processes are unchanged. Raising a level
stays M3.9.
