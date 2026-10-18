# ADR-0110 — Corrections are counted per process and action, and a level falls by rule

**Status:** accepted · extends ADR-0039 (a level is applied at the step boundary, and rises only where a version is registered), ADR-0023 (a rule decides) and ADR-0107 (an incident raised by rule) · issue #429, UC-7.5

## Context

At levels 1 and 2 a person sees every step Taktus proposes before it acts (ADR-0039). At level 2
the person confirms the step. At level 1 the person performs the act and reports it performed.
Nothing else could be said. A person who changed the proposal had no way to say so. A person who
refused it could only leave the run waiting.

UC-7.5 asks for more. Every decision on a proposal records whether it was released, corrected or
rejected. The share that was corrected or rejected is the evidence a raise rests on. A level
falls by rule when a process breaches an anchor, or when that share rises above the tenant's
limit. Nobody approves the way down.

Until now no level could fall at all. A level lives in the version's statement (ADR-0026). It
changes only where a version is registered (ADR-0039 §3). A run carries its levels from its start.

Six questions had to be answered. What is a decision on a proposal, and where is it recorded?
What is counted, and over what? What is a breach of an anchor? Where is a lowered level kept, and
how does a running run take it on? How does a level that fell rise again? Who hears of it?

## Decision

### 1. A person answers a proposed step in one of three ways

A **proposal** is a step that waits at level 1 or 2 for a person (`step.awaiting`). Its document
names the step, its method, its work, its level and what holds the level. The person's answer is
a **decision on the proposal**, with one of three outcomes:

- **released**: the step is confirmed (level 2) or reported performed (level 1) as proposed;
- **corrected**: the person gives the work they released in place of the proposed one. At level 2
  the step then runs with that work, after it is checked against the step's method. At level 1
  it is what the person performed;
- **rejected**: nothing of the step runs. The step is planned again, and the run halts with cause
  `declined`. Resuming the run proposes the step again. The answer is `step.declined`, with the
  person as its actor.

`ConfirmSteps` takes `corrected`, the work per step, and `rejected`. `taktusctl run --resume RUN`
takes `--correct STEP=FILE` beside `--approve` or `--performed`, and `--reject STEP`.

A step that fell back to a person because its model was unsure is no proposal (ADR-0076). An
anchored step is decided by its decision request, not here (ADR-0042). Neither is counted.

### 2. Each decision is a ledger entry that names no person

The run records `proposal.decided` in the same transaction as the answer. Its outcome is
`released`, `corrected` or `rejected`. Its references are the process version, the run, the step
and the **action class**. The action class is the tool action whose level held the step, as
`Held.action` says. Where the process's own level held it, there is none. `LedgerEntry.json`
gains `refs.action` for it, optional, so every entry written before is unchanged.

The entry carries no actor. The answer's own entry — `step.confirmed`, `step.performed` or
`step.declined` — names who answered, as the audit requires (ADR-0015). What is counted therefore
cannot be counted per person.

The entry's `content_digest` names the **decision document** in the object store. It holds the
outcome, the level, the action class, the digest of the proposal and, for a correction, the
digest of the version released. The version released is the proposal's document with the
person's work in place of Taktus's. The change can be seen by comparing the two.

### 3. The correction rate is a rule over the ledger

A **unit** is what is counted and what falls: a process, or one action class of it. A process is
counted across its versions.

The **correction rate** of a unit over a window is corrected and rejected over all decided. A
window ends now. It starts 7 or 28 days earlier, or at the unit's last change of level, whichever
is later. A unit changes level when it is lowered, or when its process is raised
(`autonomy.raised`). Nothing decided is no rate, not a rate of nought.

The rule is pure (`governance/domain/service/corrections.py`). It reads four kinds of the ledger:
`proposal.decided`, `autonomy.lowered`, `autonomy.raised` and `autonomy.proposed`. The same
entries give the same figures. `taktusctl corrections list` prints them per unit.

### 4. A level falls one level by rule, without a person

The governance component applies the rule after every decision. The run tells it through its port
`Levels` (`run/ports/levels.py`).

- **A rate above the limit.** When the tenant's window holds at least its minimum of decisions,
  and the rate is above the tenant's limit, the unit falls one level.
- **A breach of an anchor.** After a step that acted, the run asks the tenant's anchors again. A
  step acts when it handed work to a worker, or called an outward connector operation (ADR-0039
  §2). An anchor that names the act, where the step holds no decision to perform it, is a
  **breach**. The process falls one level, whatever its rate. A step that was skipped or
  declined performed no act, and is not looked at.

A lowering raises an incident (ADR-0107): kind `anchor.breach` or `corrections.rate`. The
incident names the rule, the run, the step and the facts the rule read. For a rate those are the
window, the counts, the rate, the limit and the minimum. For a breach they are the anchors. Both
name the level before and after. In the same transaction `autonomy.lowered` records the new
level as its outcome (`level_2`), for the version and the action class. Neither entry has an
actor: Taktus acted on its own. The same breach found twice, or the same rate crossing, raises
nothing the second time.

No level falls below 1. A breach at level 1 still raises its incident, with outcome `lowest`.

The rule decides, and nothing else does: no model, no estimate, no reading of words (ADR-0023).

### 5. The tenant sets its limits

`CorrectionLimits` holds one tenant's numbers, in the table `correction_limits` (migration 0059).
A tenant that set nothing holds the shipped default (NTC-0215):

| Limit | Default |
|---|---|
| decisions within 28 days a raise needs | 20 |
| weeks the decisions counted must span | 4 |
| rate a raise stays below, over 7 and over 28 days | 5 % |
| rate above which a unit falls | 25 % |
| window that rate is counted over | 7 days |
| fewest decisions in that window for it to lower | 4 |

A raise rate at or above the lowering rate is refused: one rate would raise and lower at once.
`taktusctl corrections configure` sets them, and `corrections.configured` records who did.

### 6. A lowered level is kept beside the statement, and applied at the step boundary

The statement stays the one place where a level is set and where it rises (ADR-0026, ADR-0039
§3). A lowering is not a statement. It only caps one. It is kept as the `autonomy.lowered`
entries of the version it names.

Before a step's level is applied, the run asks the governance component which levels its version
was lowered to. Where one is lower than the run's own, the run takes it on: `Run.autonomy_level`
or `Run.actions` changes, and `run.lowered` records each change with the new level. Every later
step of the run, and every run of the version, runs at the lowered level. A lowered action whose
step already started finishes at the level it started at.

### 7. A level that fell rises only as UC-7.1 says

Registration measures the version it replaces as it runs now. A lowered level counts as that
version's level (`process/ports/levels.py`, `lowered_to`). A new version at the level the old one
was registered with therefore raises a level. It is admitted only with a person's approval and
the quality history, as any raise is. A version at the lowered level or below needs nobody.

Answering a lowering's report, or closing its incident, raises nothing.

### 8. A raise is proposed with its figures, never applied

After a decision that lowered nothing, the rule asks whether the tenant's conditions for a raise
hold. Three must: enough decisions within 28 days, a first one at least the tenant's weeks old,
and a rate below the tenant's limit over both 7 and 28 days. Taktus then records
`autonomy.proposed` with outcome `corrections`, for the version and the action class, once per
change of level. It never applies a raise.

### 9. The owner hears of both

The reporting component gains two alerts (ADR-0106). A **lowered level** is one alert per
incident. A **raise proposed** is one alert per proposal, with the figures it was proposed with,
recomputed by the rule from the entries up to the proposal. Each is said once through the
owner-facing channel. Each stays in effect until the owner answers its report. Neither clears on
its own, because only a person's act moves the level again.

## Alternatives

- **Lower by registering a new version.** Taktus would write a version whose statement names the
  lower level. A version is a person's process; one written by Taktus would have no author and no
  reason a person gave. The running run would still carry the old level until its next start.
- **A governance record that replaces the statement's level.** ADR-0039 rejected a second place
  where a level is set. A cap that can only lower is not such a place: it never raises anything.
- **Count per version.** A new version of a process would start with no evidence. The person's
  corrections are about the process, not about its version number.
- **Count a rejection apart from a correction.** A rejection is a correction of the whole
  proposal. Counting it as none would make a process that is always refused look clean.
- **Lower inside a running step.** ADR-0039 holds a level at the step boundary. A step that
  started under a level is not asked again.
- **Let a model judge whether a correction mattered.** UC-7.5 takes a person's correction as right,
  and ADR-0023 keeps a lowering with a rule.
- **Detect a breach by reading the egress entries later.** A later read would lower a process after
  more of its steps had run. The step boundary is where the next step is held.

## Consequences

- `run`: `ConfirmSteps.corrected` and `.rejected`; the kinds `proposal.decided`, `step.declined`
  and `run.lowered`; the port `Levels` with `LoweredLevels`, `ProposalDecided` and `Breach`;
  `step.declined` in the published table of states and in `Changes.json`.
- `governance`: `CorrectionLimits`, `Unit`, `Rate`, `Figures`, `Lowered`, `Proposed`; the rule
  `domain/service/corrections.py`; the use case `Corrections`; the incident kinds
  `anchor.breach` and `corrections.rate`, whose `expected_at` is absent.
- `process`: the port `LoweredVersions`; `lowered_to`; registration measures the replaced version
  as lowered.
- `reporting`: the alerts `lowered` and `raise`, with `LevelLowered` and `RaiseProposed`.
- `LedgerEntry.json` gains `refs.action`.
- Migration 0059, the table `correction_limits`.
- `composition/decisions.py` wires `Corrections` to the run and to registration;
  `composition/alerts.py` reads it for the owner.
- `taktusctl corrections list | lowered | configure`; `taktusctl run --correct` and `--reject`.

## Where this promise ends

A breach is seen only after a step the engine ran itself acted: a worker step, or an outward
connector call. An act a worker performs beyond what its step declares is not seen, because the
anchors are asked about the step's declared actions. A step whose anchor was in force at its
boundary was asked there, so a breach needs an anchor that came into force while the step ran.
The anchors are asked once, right after the step; an anchor configured later is no breach of it.

A lowering holds for the version it names. A run of another version of the process is not
lowered, and a version registered later is measured against the lowered level only where it
replaces the lowered one. A step that already started finishes at its level. A step confirmed at
level 2 whose level fell before it started waits again, for the person to perform it.

The rate counts a decision for the action class that held its step. A step held by the process's
own level counts for the process, whatever actions it uses. Levels per risk class are not built,
and level 4 counts as level 3 (ADR-0039). A correction at level 1 is what the person reports;
Taktus does not check what was performed. A correction at level 2 is checked against the step's
method and nothing else. Who may correct or reject is not checked until rights per role exist
(UC-7.3).

Every decision reads the tenant's entries of four kinds once. A tenant with many thousands of
decisions pays for that read on every answer (#522). The figures are reproducible from the
ledger; the decision documents they name are in the object store, and are as durable as it is.

`--correct` and `--reject` are on `taktusctl run` only. `taktusctl submit --resume` answers a
proposed step with a release only, and no other surface answers one yet. An alert reaches the
owner only where the tenant configured an owner-facing channel (ADR-0106).
