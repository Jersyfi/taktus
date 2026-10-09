# ADR-0039 — Autonomy is enforced at the step boundary

**Status:** accepted · builds levels 1 to 3 of ADR-0026's statement into the product

## Context
Every process carries an autonomy statement: its level, the reason for it, and what is missing to
go higher (ADR-0026). Until now the level was a number the run carried and nothing read. A process
at level 2 ran exactly like one at level 3. Whether a person confirmed anything was left to the
bundle and to whoever ran it.

UC-7.1 asks for more (issue #78, provisional under DEC-0069). A level is set per process and per
tool action, and the lowest that applies to a step holds. Each level behaves as its name says.
Only a person raises a level, and only on a quality history. From level 3 a step runs only on an
adapter whose maturity is *verified* (NTC-0051). No level switches off the emergency stop, the
reports or the duty to escalate.

Three questions had to be answered. Where is the level applied? What does a level ask before a
step starts? Where can a level rise?

## Decision

### 1. Levels per process and per tool action, in the statement
The statement gains two optional fields (`contracts/shared/v1/Autonomy.json`):

- `actions` maps a tool action to a level of its own, with its own reason and `toward_next`. A
  tool action is a capability a step requires (`shell.script`) or a connector operation a step
  calls or waits on, with that operation's capability (`repository.pullrequest.merge`,
  `repository.pullrequest`).
- `history` is the quality history a raise needs: how many runs in a row, the most recent ones,
  ended without a failure or a result defect.

A step runs at the lowest of the process's level and the levels of the actions it uses. An
action's level above the process's would never apply; the bundle is refused for it. So is an
action that no step uses, since its level would never apply either. The run carries the action
levels beside its own level (`Run.actions`, migration 0016).

### 2. The level is applied at the step boundary, before anything of the step starts
The run engine applies the level before a step is estimated (`run/domain/service/autonomy.py`).

- **Level 2.** No step starts before a person confirmed it. The step waits in the new step state
  `waiting_human`, and `step.awaiting` names what it proposes by digest. A person's
  confirmation is `step.confirmed`, with the person as its actor; the step then starts as any
  step does.
- **Level 1.** A step that acts is never executed by Taktus. A step acts when it hands work to a
  worker or calls a connector operation declared outward. Its proposal is recorded the same way,
  and it waits until a person performed the act and reported it: `step.performed`, with the
  person as actor. Every other step — a rule, a read, a model's text, a wait — is the analysis
  Taktus supplies at level 1, and it runs.
- **Level 3 and above.** No confirmation is asked. A step runs only on an adapter at *verified* or
  above: the conformance suite and the removal test both passed. The engine asks the catalog's
  maturity record through a port of its own (`run/ports/maturity.py`). A step whose adapter is
  below is rejected before anything starts, with a finding that names the step and the adapter,
  and the run halts with cause `maturity`. An engine without the port runs no level-3 step on any
  adapter.

A step that waits for a person holds back only the steps that depend on it. The steps that do not
depend on it run on, and the run waits in `waiting_human` once nothing else can run. A person's
answer (`RunEngine.confirm`) continues the run in the same process, or hands it to a runner with
a job. A confirmation holds for its step: a resume does not ask again.

A rehearsal is asked for no confirmation and no maturity. It acts on nothing outside
(ADR-0030), and the removal test that rehearses a process must reach the same steps a real run
reaches (NTC-0079).

### 3. A level rises only where a version is registered
The levels live in the version's statement, so registering a version is the one place where a
level can rise. A version raises a level when its process's level goes up, when an action's level
goes up, or when an action loses its entry and so runs at the higher process level. The handler
that registers a version then needs two things. It needs the approval of a person, given with the
registration. It needs the quality history the *replaced* version names, read from the ledger.
Without either, the version is not stored, and the refusal is a ledger entry,
`autonomy.refused`, with what was missing as its outcome. With both, the raise is
`autonomy.raised`, with the approving person as its actor. A version that names no `history`
admits no raise.

Taktus may propose a raise: `ProposeRaise` reads the history, records `autonomy.proposed` and
returns the evidence. It never stores a version.

### 4. What no level switches off
The statement is closed. None of its fields reaches the emergency stop, the ledger the reports
are drawn from, or the escalation of a failing step. A run that waits for a person is halted at
once by a stop request that names its tenant.

## Alternatives
- **Levels as a separate governance record per process.** A level could have lived apart from
  the bundle, changed only through a governance command. ADR-0026 rejected a second place for the
  statement; a raise is then a version like any other change, and registration is where it is
  checked.
- **Halt the whole run at the first step that waits.** Simpler, and the rest of the run would not
  continue. UC-7.1 asks that it does.
- **Confirm every step at level 1 too.** Level 1 is "observe and propose": the person executes.
  A confirmation would let Taktus execute the act, which is level 2.
- **Ask the maturity at registration.** Which adapter serves a capability is configuration and
  can change after registration; NTC-0051 holds the rule where the step runs.

## Consequences
- `Autonomy.actions` and `Autonomy.history`; `ActionAutonomy` in the shared kernel.
- Step state `waiting_human`; run cause `person` for a run that waits, `maturity` for one halted by
  the threshold; `StepRun.confirmed_by`; `Run.actions`; migration 0016.
- Ledger kinds `step.awaiting`, `step.confirmed`, `step.performed`, `run.waiting_human`,
  `autonomy.raised`, `autonomy.refused`, `autonomy.proposed`.
- `taktusctl run --resume RUN --approve STEP` and `--performed STEP` answer a waiting run in the
  process; `taktusctl submit --resume RUN --approve STEP` hands it back to the daemon.
  `--approve-raise` approves a raise as the invoking person.
- The example at level 2 now waits for a confirmation at every step, as its statement says.
- Nothing is *verified* today: the conformance half of maturity is not recorded (#93). Until it
  is, a real run of a level-3 process halts at its first step that needs an adapter. The project's
  own P-01, P-02, P-03 and S-01 are at level 3 or 4; S-01 reaches only the loopback connector,
  which is no integration, and runs.

## Where this promise ends
A level is applied to a step before it starts. A step that started under an earlier rule — an
existing run's step that was already admitted — is not asked again. Level 4 is applied as level 3
until `0.6.0` builds it. Levels per risk class are not built: the risk classes are a tenant's
configuration that does not exist yet. Who may confirm a step or approve a raise is not checked:
any identity the tenant knows may, until rights per role exist (UC-7.3). The
quality history counts failures from the ledger; result defects are counted only for runs a
caller names, because nothing records them before `0.5.0`. The maturity threshold holds for the
adapter the configuration resolves, not for every adapter that could serve the step. A person
reporting an act performed at level 1 is trusted: Taktus does not check the act happened, and the
step produces no result a later step can read.
