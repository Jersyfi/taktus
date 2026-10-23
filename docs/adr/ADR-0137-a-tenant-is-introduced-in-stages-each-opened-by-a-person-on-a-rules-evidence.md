# ADR-0137 — A tenant is introduced in stages, each opened by a person on a rule's evidence

**Status:** accepted · extends ADR-0026 (autonomy carries its reason), ADR-0039 (a raise needs a
person and a history), ADR-0110 (a level falls by rule) and ADR-0023 (a rule decides a stop) ·
issue #434, UC-9.6

## Context

A business that adopts Taktus already runs. People and tools do the work today, and the work
must go on while Taktus takes over. UC-9.6 asks that Taktus carry that path in stages: a tenant
declares them, each opens only once the previous one measurably holds and a person approves, and
a stage that stops holding falls back by rule. UC-03 §5 names six such stages for a small software
business, Taktus's second tenant (DEC-0199).

Three mechanisms exist already. A level rises only by a version a person approves with a quality
history (ADR-0039). A level falls by rule, without a person, and rises again only by such a
version (ADR-0110). A rule decides every stop, never a model (ADR-0023). A stage is a frame
around all three: it limits how far a raise may go, and it adds a reason to fall.

## Decision

### 1. A tenant declares its stages as one plan

A **stage plan** is one tenant's configuration, stored under the tenant's identifier
(`StagePlan`, table `stage_plan`). It names:

| Field | Meaning |
|---|---|
| `responsible` | the role a proposal to open a stage and a stage that stopped holding are reported to |
| `blueprint` | the blueprint the plan comes from, if any |
| `stages` | the stages, in the order they open |

A **stage** names an identifier, a name, the processes it adds with the level each may reach once
the stage is open, and its **holding condition**. The condition is a rule over the ledger, made of
six figures. Every figure is optional; one left out does not bind.

| Figure | Holds when |
|---|---|
| `weeks` | the stage has been open at least this many weeks; it is also the window the others are counted over |
| `runs` | at least this many runs of the stage's processes finished within the window |
| `missed` | at most this many expected runs of them were missed (ADR-0107) |
| `incidents` | at most this many incidents were raised about them |
| `correction_rate` | no process or action class of them has a correction rate above this (ADR-0110) |
| `undecided` | at most this many of their proposals wait for a person |

A window of zero weeks begins when the stage opened. Rehearsals count for nothing (ADR-0030).

`taktusctl stage declare` stores a plan. The ledger records `stages.configured` with the plan's
digest and who declared it. A plan is refused, and `stages.refused` records why, when it:

- names a person where it names a stage, a process or the responsible role (principle 14): a
  name the tenant knows as an identity is a person;
- names a responsible role the tenant's owner-facing channel does not carry: nobody could be told;
- makes a condition looser than the blueprint it names (§6);
- would leave a process running above the level the plan allows it (§2).

### 2. A stage not yet open caps its processes at level 2

A process that a stage names may run at most at its **ceiling**:

- the highest level an open stage that names it grants it;
- level 2, while no open stage names it.

A process no stage names has no ceiling. A stage that stopped holding grants nothing until it
holds again.

Registration is where a level rises (ADR-0039). It asks the governance component for the
process's ceiling, through the process component's port `StageCeilings`. A version above it is
refused with `RaiseRefused`, and `autonomy.refused` records outcome `stage_not_open`. The
finding names the stage and what its opening lacks. A ceiling never raises anything by itself:
a version up to the ceiling still needs the approval and the history of ADR-0039.

A stage lifts a ceiling and nothing else. An anchor keeps a legally binding act, a strategic
act and the correction of a result that left the system with a person at every level, and so
at every stage (ADR-0008, ADR-0022, UC-7.1).

### 3. A person opens a stage, on the rule's figures

`taktusctl stage open <stage> --by <identity>` opens a stage. It is refused, and `stage.refused`
records the reason as outcome, unless every one of these holds:

- every earlier stage is open (`out_of_order`), and this one is not (`open`);
- the stage before it holds now, by its condition over the ledger (`predecessor`);
- every process it adds has current takeover instructions (UC-6.3, `instructions`);
- a person the tenant knows approves (`no_approval`, `unknown`).

The first stage has no predecessor. An opened stage is `stage.opened`, with the person as actor.

Taktus proposes; it never opens. When a stage holds and the next one is not open, the elected
scheduler records `stage.proposed` for the next stage once, and reports it to the responsible
role with the figures the rule read.

### 4. A stage that stops holding falls back by rule

The elected scheduler looks at every open stage once an hour, under the same rule.

- A stage whose condition holds for the first time, or again, is `stage.held`.
- A stage that held and whose condition no longer holds is `stage.fell`. It grants nothing
  from then on. Every process it adds that runs above its ceiling without the stage falls to
  that ceiling. Each fall is an incident of kind `stage.fell` with the figures the rule read,
  and `autonomy.lowered` names the new level, as ADR-0110 lowers a level. The run takes the
  lowered level at its next step boundary.
- The stage that fell is reported to the responsible role.

A level that fell rises again only by a version a person approves with its history (ADR-0039).
A stage that holds again grants its levels again; it raises nothing itself.

Nobody approves a fall, because a fall makes the system safer (UC-7.5 §1). The decision is a
rule over ledger entries, never a model (ADR-0023).

### 5. The stage view is computed, never entered

`taktusctl stage show` prints every stage of the plan with its state, its condition, the figures
it reads and what is missing. The states are `closed`, `open`, `holding` and `not_holding`.
For an open stage, *missing* names each part of its condition that does not hold. For a stage
not yet open, it names what its opening lacks: the predecessor's unmet figures, the takeover
instructions, a person's approval. Every figure is read from the ledger at the moment of the
view. The view names stages, processes and roles, never a person.

### 6. A blueprint proposes the stages, and its conditions are a floor

A blueprint may carry the stages it proposes, as `stages.yaml` beside its `blueprint.yaml`.
`blueprints/software-operations/stages.yaml` carries UC-03's six. A tenant's plan that names a
blueprint holds every condition of a stage the blueprint also names at least as strictly as the
blueprint does. Stricter means: `weeks` and `runs` no lower, every other figure no higher, and
no figure the blueprint binds left out. Which processes a stage adds stays the tenant's
(UC-9.6 §3).

### 7. Where it lives, and what it reads

The rule lives in the governance component, which owns the levels that fall and the incidents.
UC-9.6 is filed under `value`, as part of steering the transformation (UC-9.2). The component
reads the ledger itself. Through ports answered in the composition root it reads three things:
the level a process runs at now, from the process component and the lowered levels; whether a
process has current takeover instructions; and the owner-facing channel, to report. `refs.stage_id`
in `LedgerEntry` names the stage an entry is about.

## Alternatives

- **The stage as part of the autonomy statement.** Every version would repeat the tenant's
  plan, and opening a stage would need a new version of every process in it. A stage is the
  tenant's frame, not a property of one version.
- **Opening a stage opens its levels.** The stage would raise processes without their own
  history. A stage only lifts a ceiling; each raise stays ADR-0039's.
- **A fall of one level, as ADR-0110 falls.** A stage that stops holding would leave a process
  at level 3 when the stage that granted it level 4 fell. The ceiling without the stage is what
  the stage's absence allows, so the fall goes there.
- **Taktus opens a stage when the rule says it holds.** UC-9.6 §2 forbids it.
- **The stage state as a stored record.** It would be a second place beside the ledger; the
  ledger already holds every opening, holding and fall.

## Consequences

- `governance`: `domain/model/stages.py`, `domain/service/stages.py`,
  `application/service/stages.py`, `ports/stages.py`; `IncidentKind.STAGE`.
- `process`: the port `StageCeilings`; registration refuses a version above its ceiling.
- `composition/stages.py` answers the ports, and the scheduler's tick looks once an hour.
- Migration `0073` adds the table `stage_plan`.
- `LedgerEntry.json` gains `refs.stage_id`, optional: every entry written before is unchanged.
- `taktusctl stage declare|show|open|look`; `look` makes the scheduler's look by hand.
- `blueprints/software-operations/stages.yaml` declares UC-03's six stages (NTC-0232).

## Where this promise ends

The takeover instructions of UC-6.3 do not exist on a process version yet. Until they do, the
composition root answers that no process has them, and no stage opens on an instance. This
holds UC-9.6's rule strictly; it does not make it usable before UC-6.3. The ceiling is enforced
where a version is registered. A version that already ran above it when the plan was stored is
refused at declaration, not lowered. A stage that falls lowers the processes it adds, not the
stages after it; those show their predecessor as not holding and keep their own grants. The
figures are counted from the ledger entries of their kinds at every look, not from a
projection; a tenant with years of entries pays for that at every look. The proposal and the
fall reach the responsible role only where the tenant's owner-facing channel carries it; the
ledger and the view hold them either way. The view is on the command line; the web app does
not show it yet. The plan of the second tenant is its configuration on its own instance and is
not in this repository; the blueprint proposes it. The instance does not carry the blueprints:
the floor a plan is held to is the `stages.yaml` the operator hands over with the plan, and the
plan records the blueprint's name, not its digest.
