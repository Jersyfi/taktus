# ADR-0160 — Level 4 is unattended in execution and heals within its frame

**Status:** accepted · builds level 4 of ADR-0026's statement into the product, after ADR-0039
built levels 1 to 3 · issue #645, UC-7.1, UC-4.6

## Context

ADR-0039 enforces levels 1 to 3 at the step boundary. It applied level 4 as level 3 until
`0.6.0`. A process at level 4 therefore behaved exactly like one at level 3.

The levels are named by the role a person plays (UC-7.1 §1). At level 3 the person is *on* the
loop: they watch reports and samples and step in. At level 4 the person is *out* of the loop:
they set frame and goals and are drawn in only when the frame is exceeded. Level 4 is
*unattended in execution, anchored in direction and in outward correction* (ADR-0008,
ADR-0022, UC-7.1 §4).

At level 3, three things draw a person in during a run: an anchor, an action set lower, and a
failure. A failed step escalates, and a person resumes the run. Only the third is out of place
at level 4. A retry of a failure Taktus knows is a correction within the frame: UC-4.6 asks for
exactly that, and the control plane's states name it, `self-healed` (control-plane.md §5.2).

Three questions had to be answered. What does level 4 do that level 3 does not? What is the
frame of a heal? What stays with a person whatever the level?

## Decision

### 1. Level 4 differs from level 3 in one place: a failure inside the frame is healed
Before a step starts, level 4 asks what level 3 asks: no confirmation, and a *verified* adapter
(ADR-0039 §2). After a step failed, the run engine asks the rule `run/domain/service/healing.py`
whether Taktus heals it. When it does, the engine records `step.healed`, with outcome `retry`
and the failure it answered by digest, and admits the step again at once. The heal passes
admission like any retry, recorded as `step.retried` (ADR-0147 §4). What it led to is the
step's next `step.finished`. When it does not, the run escalates as at every level, and the
reason says why it was not healed.

A level-3 step's failure escalates without a heal, as before. The person is on the loop there,
and a resume is theirs.

### 2. The frame of a heal
A failure is healed only when all of this holds:

- the step runs at level 4: the process's level, and no action of the step set lower;
- the run is no rehearsal, which is asked no level (NTC-0079);
- an adapter classified the failure as one the same call may be repeated after
  (`StepRun.retryable`). A failure nobody classified is not of a known kind: a rule that failed,
  a check that disagreed, a worker's own failure. It escalates (UC-4.6 §2);
- the step is not blocked for want of an adapter. A missing configuration is not healed by
  asking again (ADR-0046);
- the call may be repeated without a second effect. An outward operation with
  `idempotency: none` is never repeated by Taktus on its own (ADR-0024 §3);
- no stop was requested; a stop takes effect at the boundary;
- the step was healed fewer than **two** times in the run (`HEALS`). The third failure
  escalates, and its reason names the heals tried.

A heal reserves against the run's budget as every step does (ADR-0005). One that does not fit is
refused, and the run halts with cause `limit`. A failed step produced nothing that left the
system, so a heal changes nothing outside it (ADR-0022). A retried connector call keeps its
attempt and its idempotency key, so a target that saw the first call recognises the second.

What a failure was classified as now holds for that failure only: a worker step's admission
clears `retryable` as a local step's always did. A failure after a heal is judged by its own
classification, never by the one before it.

### 3. What no level changes
An anchor halts a level-4 run at the step boundary with a decision request, as at level 1: a
legal anchor, a strategic anchor, the correction anchor, the frame's own anchors and a step's own
`ask` (ADR-0042, ADR-0088, ADR-0130, ADR-0142). A heal never passes an anchor: the step's
anchors were asked before it first started, and a heal is the same step at the same boundary.
The emergency stop, the reports and the escalation duty apply at level 4 (ADR-0039 §4). The
statement gains no field.

### 4. A raise to level 4 is a raise like any other
A raise to level 4 needs a person's approval and the quality history the replaced version names,
as ADR-0039 §3 says. Taktus may propose it, and never applies it. At level 4 the statement
carries no `toward_next`: there is no next level (ADR-0026). A tenant of one person sets level 4
like any other tenant.

## Alternatives
- **Level 4 as level 3 with nothing added.** The issue that asked for level 4 names the defect
  of that: a level-4 run drew a person in on every failure, which is level 3.
- **Heal at level 3 too.** Then level 3 and level 4 would again behave alike. A person on the
  loop also resumes a run; that is what "on the loop" means.
- **Heal every failure at level 4.** A failure nobody classified may be anything: a wrong rule,
  a check that disagreed, a worker that broke. Repeating it heals nothing and hides it.
- **A delay between heals.** A provider that is briefly unavailable often answers a second later,
  and a delayed retry needs a parked job. The bound of two immediate heals keeps a heal inside
  one pass of the run. A failure that outlasts it reaches a person.
- **The bound in the statement.** A per-process field would let a bundle widen its own frame.
  It stays a constant until a use case asks for one per process.

## Consequences
- `run/domain/service/healing.py`; the engine records `step.healed` and admits the step again.
- A level-4 process whose connector step fails with a retryable failure now finishes without a
  person where a heal succeeds; before, the run escalated. P-03 of this project is at level 4.
- A healed run still had a failure: its `step.finished` with outcome `failed` keeps it out of the
  quality history (ADR-0039 §3).
- An escalation at level 4 says why the failure was not healed.

## Where this promise ends
A heal is a retry of the same step with the same work. It is not a correction of a result, a
change of the process (UC-4.3) or a move to another adapter. Only failures an adapter classified
as repeatable are healed; a worker's failure is not, until the worker contract classifies its
failures. The bound of two heals is per step and per run, not configurable, and a resumed run
does not get its heals back. Service-level objectives and the improvement proposal after the same
failure healed three times (UC-4.6 §2) are not built here. Levels per risk class are not built:
a tenant's risk classes select anchors, not levels (ADR-0039). Who may approve a raise to level
4 is not checked beyond what ADR-0039 checks.
