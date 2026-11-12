# ADR-0215 — A class of request a step's result names carries its own level

**Status:** accepted · extends ADR-0039 (a level per process and per tool action, the lowest
holding) and ADR-0110 (corrections counted per unit, a level falls by rule) · UC-7.1, UC-7.5,
UC-03 B-3.03, DEC-0228

## Context

UC-03 §3 says that one process may send an approved class of reply at level 3 and hold every
other class at level 2. B-3.03 is that approval: the business releases one class of support
replies — say, questions how the product is used — for sending on its own, on the evidence of
its corrections. Every other class stays with a person.

The product held levels per process, per tool action and per risk class (UC-7.1, ADR-0170).
None of them can say "this class". The class is not known when the run starts. It is what a
step reads from the customer's message, and every reply is sent by the same operation. The
corrections were counted per process and per action (ADR-0110), so a class gathered no
evidence of its own either.

UC-03 §5 states the numbers the catalogue uses: a raise after 20 runs over four weeks with a
correction rate below 5 %; a fall at once on a breach of what stays with a person, and
otherwise at two corrections a week. These are a blueprint's proposal, not the product's.

## Decision

### 1. The statement names its classes

`Autonomy.classes` (`contracts/shared/v1/Autonomy.json`) names:

- `step`: the step whose result names the class, and `select`, the path of the class in that
  result, where it is not the result's text;
- `levels`: each class the process knows, with its level, its reason and what it lacks to rise,
  as an action's level is stated;
- `default`: the level of an answer that names no class the statement knows;
- `limits`: when a class rises and when it falls (§4).

No class and no default is above the process's level: the lowest level holds, as it always
did. A process that releases one class therefore runs at level 3 itself, its default at 2.
Registration refuses a class step that is not a step of the process, and classes that no step
depends on.

### 2. A class holds the steps that depend on its step

A step that depends on the class step, directly or through other steps, runs at no higher a
level than its class. Steps that do not depend on it run at the process's and their actions'
levels. When the first dependant reaches its boundary, the run reads the class step's result
once. Its text is stripped of space and closing punctuation and put in lower case. A class the
statement lists is recorded on the run as `case_class` and in the ledger as `run.classified`,
outcome `named`, with `refs.case_class`. Any other answer is recorded `unnamed`; its dependants
run at the default.

The run takes the statement on when it is created, from the version, through the port `Levels`
(`run/ports/levels.py`), as it takes the lowered levels.

### 3. Every decision on a step its class held counts for the class

`Held` names the class that holds a step. A class named holds where its level equals the
process's: at level 2, where every class is at 2, the decisions of each class count for that
class, so that it gathers the evidence a raise rests on. An action whose level is lower than the
class's holds over it. `proposal.decided` carries `refs.case_class`
(`contracts/shared/v1/LedgerEntry.json`). A unit of the correction rate is a process, an action
of it, or a class of it — never an action and a class at once.

### 4. A class rises and falls by the limits its statement names

A class is counted by its statement's `limits`, never by a product default:

| Limit | Means |
|---|---|
| `raise_decisions` | decisions of the class within 28 days a raise is proposed on |
| `raise_weeks` | weeks those decisions must span |
| `raise_rate` | the correction rate a raise stays below, over 7 and 28 days |
| `lower_corrections` | corrected or rejected decisions that lower the class one level |
| `lower_days` | the window those corrections are counted over |

A class falls one level once `lower_corrections` decisions of it within `lower_days` were
corrected or rejected. It is the rule of ADR-0110 §4 with a count in place of the rate. The
incident is `corrections.rate`, its facts the counts and the limit; `autonomy.lowered` names the
class. A breach of an anchor lowers the whole process at once, as before. That holds every class
at or below the lowered level.

A raise is proposed as ADR-0110 §8 says, on the class's limits, with `autonomy.proposed`
naming the class. It is never applied.

### 5. A class rises only through a version a person approves

Registration counts as a raise a class whose level rises, and a default that rises. Each needs
a person's approval and the quality history, as any raise does (ADR-0039 §3). A class lowered by
rule counts at its lowered level (`lowered_to`), so a new version at the old level raises it.

### 6. The blueprint proposes its numbers

B-3.02 version 3 of `software-operations` classifies the message with a model (`classify`,
purpose `check`) into `how_to`, `bug`, `account`, `billing` and `feedback`, every class and the
default at level 2. Its limits are UC-03's: 20, four weeks, 5 %, two corrections within seven
days. Its `history` is 20 runs, so that a raise can be admitted at all. A tenant releases a class
by registering its own version at level 3 with that class at 3.

## Alternatives

- **A process per class.** Each would need its own trigger on the same mailbox and its own
  copy of the steps, and a message would start every one of them.
- **A class as a tool action.** An action is a capability or an operation the step calls. A
  class is a value the run reads; naming it as an action would make the action table say
  something it does not.
- **Let a class level be above the process's.** The lowest level holds, everywhere else in the
  product. A class above the process would be the one exception, and would make a process at
  level 2 send on its own.
- **The tenant's correction limits for classes.** UC-03 states a count per week for a class, not
  a rate; the statement carries the class's numbers so that a blueprint proposes them and a
  tenant's version changes them.
- **A model decides whether a class is released.** The class is read by a model. Whether its
  level is released is the statement's and a person's (ADR-0023).

## Consequences

- `shared/v1`: `ClassAutonomy`, `ClassLimits`, `Autonomy.classes`, `Autonomy.class_level`,
  `depending_on`; `LedgerRefs.case_class`.
- `run`: `Run.classes` and `Run.case_class`; `run.classified`; `Held.case_class`;
  `autonomy.class_of` and `class_named`; the port `Levels.classes`; lowered classes taken on as
  `run.lowered` with `refs.case_class`.
- `governance`: `Unit.case_class`; `Lowered.classes`; `CorrectionLimits.lower_corrections`;
  `DecisionMade.case_class` and `class_limits`.
- `process`: registration finds a class raised, refuses a class step that is not a step.
- `composition/decisions.py`: `LevelsOfTheRun` reads the version's classes.
- `blueprints/software-operations`: B-3.02 version 3.

## Where this promise ends

- The class is read once per run, from the first result of the class step. A step corrected
  after the class was read does not change it.
- A class is a value the statement lists. A model's answer outside that list holds the default
  and counts for the process. A wrong class from the model is not caught by this rule; the frame
  of ADR-0142 still checks every reply, whatever its class.
- A step that does not depend on the class step runs at the process's level. A process that
  releases a class runs its reading and drafting steps at level 3, and so only on verified
  adapters (UC-7.1).
- A class lowered by rule holds for the version it names, like any lowering (ADR-0110).
- Every engine construction outside the composition root that leaves the port `Levels` out
  runs no class: a test or a tool that builds its own engine without it runs every step at the
  process's and the actions' levels.
- No figure names a person (principle 14). A class is a kind of request, never a customer.
