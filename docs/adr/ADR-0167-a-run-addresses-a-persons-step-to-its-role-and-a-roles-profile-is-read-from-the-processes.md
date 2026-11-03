# ADR-0167 — A run addresses a person's step to its role, and a role's profile is read from the processes

**Status:** accepted · extends ADR-0146 (a human step and a fallback to a person name a role), ADR-0015 (no figure assesses a named person), ADR-0029 (reporting reads and owns no figure), ADR-0043 (blocked-time accounts) and ADR-0159 (value streams) · issues #331 and #344, UC-4.20 and UC-15.7

## Context

ADR-0146 put a role on every `human` step and on every fallback to a person. It stopped at
registration. Its promise ended where a run waits: the wait was shown to whoever may see the
run, and it named no role.

A second gap sat underneath. A `human` step of the organisation had no executor at all. Only a
participant outside the organisation (ADR-0155) could answer one. A run of a process with a
person's own step was refused before it started, with "no executor for method human".

Issue #344 asks for a third thing that rests on both: a **role profile**. A role profile is a
page that says, for one role of the tenant's structure, what the processes need of it. It lists
the value streams it serves, the steps it performs, what it decides and supervises, what it must
be able to take over, the expertise needed, its load now and if Taktus stopped, what waits at
it, and the requests open for it. It can be exported as a draft position description. It is
never a file about a person.

A role profile is close to personnel work. German labour law gives a works council a say over
technical systems that can monitor the behaviour or the performance of employees (§87(1) no. 6
BetrVG). DEC-0029 asks for a labour-law review before anything personnel-related is used. It is
open, and NON-BLOCKING.

## Decision

### 1. A person's own step waits for its role

A `human` step whose work names no `participant` is performed by a person of the organisation.
Its work is empty, or names the `task` in one sentence. Nothing else is accepted.

At the step's boundary the tenant's anchors are asked first, as for every step (ADR-0042). Then
the step waits for a person of its role, **at every autonomy level**. No level performs a
person's step for them.

- The step's block is booked to `wait.human` with the cause `awaiting_role`, and it carries the
  step's role. A step that names no role waits with no role, as a tenant without a structure
  registered it (ADR-0146 §2).
- `step.awaiting` names, by digest, what is asked: the step, its role, its expertise and its
  task. It names no person.
- The steps that depend on it are held back. The others run on.
- A person answers through the same answer as a level-1 step: *performed* or *rejected*.
  Performed, the step succeeds with method `human` and hands on no result of Taktus's
  (ADR-0018). Rejected, nothing of it is done and the run halts with cause `declined`; a resume
  asks again. A correction is refused, because Taktus proposed nothing to correct.
- A rehearsal asks nobody. The step ends rehearsed, as a participant's step does.

### 2. A fallback to a person is addressed to the fallback's role

When a model is unsure and its step falls back to a person (ADR-0076), the block carries the
role the fallback names. Every view that already shows a wait's role shows it: the run level
("addressed to the role …"), the stages, the variants and the value-stream lanes.

### 3. A role's profile is derived from records that exist

The profile is a view of the reporting component. It reads and stores nothing of its own
(ADR-0029). The composition root gathers it from the components that hold the facts:

| What the profile says | Where it is read |
|---|---|
| the streams the role is responsible for and those it serves | the process component's value streams |
| the steps it performs, with their task and expertise | the active versions' `human` steps of the role |
| what it must be able to take over | the active versions' fallbacks to the role |
| what it decides | the tenant's anchors whose decider is the role, and steps whose `ask` names it |
| what it supervises | checks of kind `approval` or `sampling` that name the role |
| the expertise needed | the union of the expertise of the steps and fallbacks above |
| its load now | the waits open now that are addressed to it, and the steps of it performed in the window |
| its load if Taktus stopped | the steps Taktus performs whose fallback is the role, and how often they ran in the window |
| what waits at it | the time steps waited at it in the window, from the blocked-time records |
| open proposals | the decision requests not yet applied whose decider is the role |

A step without a role counts for the role `owner`, as the stage view and the value stream
show it (UC-6.15, UC-15.6).

### 4. No figure of the profile names a person

- Every figure that a person's work produced is withheld where fewer than two identities hold
  the role: the time waited at it and the steps of it performed. The withheld field keeps its
  name and says why (ADR-0015, NTC-0168).
- A reader who holds the role sees their own waits at it beside the role's figure, under their
  own name only.
- What Taktus does is the process's and is never withheld: the load if Taktus stopped.
- The profile states what the processes need of the role. It carries no field for whether a
  person is needed, how many, or which one. A workforce decision is a strategic anchor
  (ADR-0008).

### 5. The export is a draft, and says it is unreviewed

`GET /roles/{role}/description` returns the profile as a draft position description in Markdown.
It carries no figure of time and none of the reader's own. Its first lines say that it is a
draft and that it is not to be used before the labour-law review that DEC-0029 names. Every
profile read carries the same statement in `review`.

## Alternatives

- **Keep a person's own step without an executor.** Rejected: a process with a person's step
  could not run, and the role ADR-0146 put on it had no effect at run time.
- **Run a person's step through a decision request.** Rejected: a decision request decides
  whether an act is performed (ADR-0042). A person's own step *is* the act. Its answer is that
  it was performed, which is the answer a level-1 step already has.
- **Store the profile.** Rejected: it would be a second copy of the processes' facts, out of
  date as soon as a version changes (ADR-0029).
- **Withhold every figure below two holders.** Rejected: what Taktus performs is the process's
  figure, which principle 14 asks to be analysed. Only figures that persons produced are
  withheld.
- **A headcount or capacity field.** Rejected: the issue forbids it. Whether a person is needed
  is not a question the processes answer.
- **Not building the profile before the review.** Rejected: the review needs something to
  review. It is built, marked, and not to be used before it.

## Consequences

- `run.domain.model.HumanWork`; `parse_work` returns it for a `human` step without a
  participant. The block cause `awaiting_role`.
- `RunEngine` opens the block with the step's role, and the fallback's block with the
  fallback's role; `confirm` answers a person's step as described in §1.
- `reporting.domain.service.profiles`, pure; `composition.profiles.RoleProfiles`, which gathers
  the facts; `GET /roles`, `GET /roles/{role}` and `GET /roles/{role}/description`.
- ADR-0146's promise end on run time is lifted by §1 and §2.

## Where this promise ends

- **No right per role on the answer.** Any identity that may answer a run answers a person's
  step, as before (UC-7.3). The wait is addressed to the role; it is not locked to it.
- **No notification of the role's holders.** The wait is shown where waits are shown. A message
  to the holders of a role is the owner-facing channel's, and not built here.
- **No takeover role.** A person who takes a running step over (ADR-0128) is not asked for a
  role.
- **The profile is unreviewed.** It is built and marked. It is not to be used in earnest before
  the labour-law review that DEC-0029 names has covered it, for the tenant's jurisdiction.
- **Only active versions.** The profile reads each process's active version. A version that is
  not active contributes nothing.
- **A fallback performed by hand counts as Taktus's.** A step that a person performed after its
  model was unsure keeps the model's method on its step run. The load if Taktus stopped counts
  it as Taktus's run. The figure errs towards what would come to the role.
- **No web page.** The profile is read on the HTTP surface. A page in the web app is later work.
- **No person's file, ever.** Nothing here joins a profile to the identities that hold the role.
