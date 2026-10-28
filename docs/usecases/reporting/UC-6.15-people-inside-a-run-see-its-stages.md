---
id: UC-6.15
title: People inside a run see its stages
component: reporting
epic: E6
serves: [P7, P14]
state: specified
version: 0.5.0
tests: []
adrs: {ADR-0015: 3a42705e5561, ADR-0029: 37c061ef032a, ADR-0055: 182c84e9cdbd}
supersedes: null
---

# UC-6.15 — People inside a run see its stages

## 1. What must be achieved

A person who takes part in a run and is not technical sees the run as its **stages**, without the
step graph. A stage is a stretch of the run named in words a participant knows. For each stage the
person sees whether it is done, whether it is current, or whether it still lies ahead. Where a stage
waits, the person sees for whom it waits, named by a role, never by a person.

The stages are a second way of reading the run level of UC-6.10, for a reader who has no use for
steps, methods or exactness classes. They are not a second process.

## 2. How it is verified

- **Drawn from the same records, and stores nothing.** The stage view is computed on each request
  from the records the run level of UC-6.10 reads: the registered version of the process and the
  run's records. A test changes the version or the run and finds the stages changed with nothing
  else edited. A test finds that the view holds no table, no file and no ledger entry of its own.
- **Each stage has exactly one state.** Every stage is *done*, *current* or *ahead*. A run that
  has ended shows every stage done or, where the run failed or was halted, the stage it stopped at,
  with the state of the run in words. A test covers each state.
- **Waiting names a role.** A stage that waits for a person or a decision names the role it waits
  for. It never names a person. A step whose wait has no role is shown as waiting for the owner,
  never as waiting for nobody.
- **Agrees with the run level.** For every run in a test, the stage the view calls current holds
  the step the run level shows as under way or waiting, and a stage is done only when every step in
  it is done. A disagreement fails the test.
- **No step graph.** The view shows no step, method, exactness class or glyph of the run level's
  vocabulary. The step a stage stands for is reachable by a link to the run level, for a reader who
  may see it.
- **Only what the reader may see.** A run the reader may not see (UC-6.4) is answered exactly as
  one that does not exist.
- **No person assessed.** No figure in the view has a named person as its subject, and no duration
  of a stage is computed per person (principle 14, ADR-0015).
- **Readable without sight of colour or motion.** Every stage has a text equivalent with its name,
  its state and, where it waits, the role (UC-6.10).
- **Live.** A change of a stage's state reaches every open view within 5 seconds, without the
  reader reloading (ADR-0055).

## 3. Where the boundary lies

**Not a separate process model.** A stage is read from the version's own steps. Nobody draws or
maintains stages apart from the process, and a process with no stage names yields one stage per
step the participant is concerned with, not an invented grouping. **Not a replacement of the run
level.** The step graph stays for those who need it. **Not a new right.** The view shows nothing
of a run that its reader could not see at the run level. **Not a way to answer.** The view shows
who is waited for; answering a decision request stays with UC-7.4. **Not a measure.** It shows
where a run stands, not how fast a role or person is.

## 4. What it rests on

The run level and the visual vocabulary of UC-6.10 and the stream of changes (ADR-0055); what each
role sees (UC-6.4); the rule that no figure assesses a named person (ADR-0015); the `reporting`
component, which owns views and no figure (ADR-0029). A human step that names a role is #331. The
owner accepted it as F9 of the product outlook (DEC-0190); the source is
`docs/research/2026-10-12-market-review.md` §2.2.5. Issue #335 carries it. The version is `0.5.0`,
the milestone DEC-0190 places it in.
