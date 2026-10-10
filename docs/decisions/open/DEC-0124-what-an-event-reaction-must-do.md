# DEC-0124 — What an event reaction must do

**Category:** NON-BLOCKING
**Raised in:** [#175](https://github.com/Jersyfi/taktus/pull/175), while making issue #76 ready: no use case says what an event reaction must do
**Issue:** [#172](https://github.com/Jersyfi/taktus/issues/172)
**Needed by:** 2026-10-24
**Provisional answer:** Option A. The new use case UC-4.14, *A process starts on what happens in a tool*, is in force as written and binds the change that builds event reactions (#76). Marked here, in UC-4.14 §4, and in issue #76.

## 1. What this is about

Taktus can start a process in two ways today: a person starts it, or a clock does, on a schedule.
The third way is planned for the current version: a process starts by itself when something
happens in a tool the organisation works in. An issue is labelled *ready*, and the process that
implements issues starts. A pipeline fails, and the process that looks into failures starts.
This is what lets Taktus run its own development processes without a person starting each run
(issue #87).

The task that builds it (#76) could not be started, because three things were missing. Two of
them are technical and were settled in the same change as this request: the list of happenings
Taktus understands and how a process says which of them start it (the *events contract*), and
how one happening starts a process exactly once even when it is reported twice or arrives while
Taktus is restarting (ADR-0048). The third is a requirement: nothing in the repository says what
an event reaction must achieve and how that is checked. Requirements are kept as *use cases*,
one file per capability, each saying what must be achieved, how it is verified, and what is not
required. That is what this request asks you to accept.

What was attempted: the task's sections "How it is verified" and "Where the boundary lies" were
to be written from an existing use case, as for every task. The nearest are UC-1.1 (*commands
from any channel*), which explicitly ends once an input has become a command, and UC-5.2
(*control inside or outside Taktus*), which only says it rests on event reactions. Neither
states a condition an implementation could be held to.

## 2. Why you are being asked

Entry M3.15 of `docs/decisions/anchors.taktus.md`: *"What a use case requires — what is new
beyond `docs/vision/` and the owner's project definition; bringing a use case up to them is M2.7: its outcome, its verification
condition and its boundary — sections 1 to 3 of a file under `docs/usecases/`; adding one,
changing one, retiring one."* This adds one.

**Sources checked:** `docs/vision/` — principles 1 (an orchestrator), 4 (any channel), 8
(repeatability) and 12 (production-ready) give the direction of the conditions but not the
conditions; it is therefore not a restoration (M2.7). The ADRs — ADR-0048 and the events
contract say how reactions are built, and ADR-0035 and ADR-0040 decide the counterparts for time
triggers and identity; an architecture decision says how something is built, not that a use case
must require it. Both anchor pages — M3.15 makes the requirement yours. The register — DEC-0030,
DEC-0069, DEC-0082 and DEC-0087 asked the same question for the use cases of the migration; none
covers a use case written outside it, and what a requirement adds stays yours under M3.15, so
the precedent is cited in the recommendation, not applied in your place.

## 3. What you must decide

Whether a new use case, UC-4.14, states what an event reaction must do, with the conditions
below — or whether the condition goes into an existing use case instead.

## 4. What you need to know to decide

**Words used here.** An *event* is something that happened in a tool, as Taktus received it: an
issue opened, a label added, a pipeline completed. A *trigger* is the line in a process that says
which events start it. A *filter* narrows a trigger to some events of a kind, such as "the label
added is `ready`". A *condition* is a state of Taktus that must hold before the run starts, such
as "there is room on the machine". A *rule* is a fixed computation that gives the same answer for
the same input; a language model is not one.

**What UC-4.14 requires**, in short (the file is `docs/usecases/process/UC-4.14-a-process-starts-on-what-happens-in-a-tool.md`):

| Condition | Where it comes from |
|---|---|
| a matching event starts one run with the inputs the trigger declares, on the automation's next pass, without a person | the task's own outcome (#76) |
| the same event delivered twice, or handled by two instances, or interrupted by a restart, starts the process once | ADR-0048, as ADR-0035 holds it for schedules |
| one event matching two processes starts one run of each; matching two triggers of one process, one run | ADR-0048 |
| whether a run starts is decided by a rule over the event alone, never by a language model | ADR-0048, after ADR-0023's emergency stop; principle 8 |
| a condition that does not hold makes the event wait, not vanish | the session: an issue labelled ready while Taktus is busy must still be implemented |
| an unplaced sender starts nothing; the run acts for the sender | UC-1.7, ADR-0040 |
| an event older than the process version does not start it | ADR-0048, as ADR-0035 refuses slots before a schedule existed |
| a trigger with an unknown event, an unknown condition or a missing input is refused when the process is registered | the events contract |
| every started run says in the activity log which trigger and event started it, without content | ADR-0006 |

**What it does not require**, in its boundary: catching events Taktus never received (a
schedule is the backstop); judgement inside a trigger (a process judges in its first step);
who may cause which process to start (UC-7.3); reacting to Taktus's own events, such as an
anchor being hit.

**Why a new use case rather than an amendment.** UC-1.1 is about turning an input into a
command, and ends there by its own boundary; adding "and then a process starts" would give it a
second outcome. UC-5.2 is about where control sits, inside Taktus or in an external tool; event
reactions serve it, and it rests on them, but they are also used where Taktus holds control. A
process starting on an event is a capability of the process engine, beside a process starting on
a schedule, so it is numbered in that area, as the next free number, UC-4.14.

**What it commits the project to.** The change that builds event reactions is held to these
conditions and cannot loosen them. Changing one later is a request of its own, never part of the
change that implements it.

## 5. Options

### Option A — a new use case, UC-4.14, as written (recommended)

- **Meaning:** UC-4.14 is in force with the conditions above; issue #76's sections are written
  from it.
- **Consequence:** #76 is built against it in `0.2.0`, and #87 can rely on it.
- **Effort:** none now.
- **Reversibility:** cheap until #76 is merged; afterwards a change is a request for that use case.
- **Why recommended:** every condition comes from an architecture decision already in force or
  makes a principle checkable, none moves a limit or an autonomy level, and where two readings
  were possible the stricter was taken — the reason you accepted for the use cases of the
  migration (DEC-0030).

### Option B — the conditions go into UC-5.2 instead

- **Meaning:** UC-4.14 is withdrawn; its conditions are added to section 2 of UC-5.2, and its
  boundary to section 3.
- **Consequence:** one use case fewer, and UC-5.2 holds two outcomes: where control sits, and that
  an event starts a process. Event reactions where Taktus holds control are then verified under a
  use case about the opposite case.
- **Effort:** an hour of a session.
- **Reversibility:** cheap until #76 is merged.

### Option C — UC-4.14, except the conditions you name

- **Meaning:** you name the conditions to change, remove or read otherwise — for example that a
  waiting condition never expires, or that the run acts for the sender rather than for whoever
  set up the process.
- **Consequence:** #76 is built on the changed use case; a session changes it in a change of its
  own first.
- **Effort:** your reading, and an hour of a session.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing: the provisional answer is in force, and #76 is built against UC-4.14 as written. If no
answer arrives by 2026-10-24, event reactions are merged on Option A, and changing a condition
afterwards costs a request for that use case instead of one edit now.

## 7. How to answer

"DEC-0124: Option A." — or "DEC-0124: Option B." — or "DEC-0124: Option C" followed by each
condition and the change you want, in issue [#172](https://github.com/Jersyfi/taktus/issues/172).
A free-text answer is read back as an interpretation and confirmed before it is acted on.
