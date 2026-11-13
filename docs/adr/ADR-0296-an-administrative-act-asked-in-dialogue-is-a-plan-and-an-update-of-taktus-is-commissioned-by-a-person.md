# ADR-0296 — An administrative act asked in dialogue is a plan, and an update of Taktus is commissioned by a person

**Status:** accepted · extends ADR-0237 (a plan is commissioned in versions), ADR-0279 (the
inventory of administrative acts), ADR-0124 (the upgrade from the release before) · respects
ADR-0013 C and D, ADR-0025 · UC-10.2, UC-1.2, UC-7.3

## Context

UC-10.2 asks that an administrative act asked of Taktus in dialogue is carried out as a plan
that a person with the right commissions (UC-1.2). It needs the same right as the same act done
by hand (UC-7.3), and never a wider one. It also asks that an update of Taktus prepared in
dialogue is applied only when a person commissions it, that the version before it can be
restored without Taktus (ADR-0013 C), and that a version Taktus built is put into production by
another instance or a person, never by itself (ADR-0013 D). No instance administers the platform
it runs on (ADR-0025).

The plan dialogue (ADR-0237) already commissions a draft as an act of its own. A draft that
works out an agent registers the agent when it is commissioned (ADR-0292). Nothing carried out
an administrative act.

## Decision

### 1. A plan draft may carry an administrative act

A draft's **administration part** names one act of the inventory, by its name, and its
arguments. The composition root states which acts a plan carries out and which arguments each
takes:

| Act | Arguments |
|---|---|
| `identity.roles` | the identity, its roles (`none` clears them) |
| `identity.revoke` | the channel link |
| `identity.grant`, `identity.withdraw` | the role, the right |
| `instance.update` | the release to update to |

Every other act of the inventory stays by hand, and the composition root states why for each:
a read is answered, not carried out; an act on the instance needs the instance's administration
key, which no identity of a tenant holds, so a plan would need a wider right than by hand; an
act that answers a key never puts the key into a plan's record; a quota, the structure and a
project are set in their own dialogues; a stop acts at once. A test holds the two lists to be the
whole inventory, with no act in both.

### 2. Choosing the act gives the steps

A draft is opened with an act — `POST /plans` with `act` and `arguments`, or the update's own
operation — or the act is set later as the field `administration`. The act gives the draft its
steps and their estimates. An identity act is one `rule` step of class `exact`: the use case both
ways in call. The guided mode asks for each argument still missing. The person states when it is
due, the autonomy level and why, as for any plan.

### 3. Commissioning checks the right, then carries out the act

Commissioning is refused, writing nothing, where the draft lacks a part or a step cannot be
estimated (ADR-0237); where the commissioner's roles do not hold `tenant.administer`, the right
the same act needs on the HTTP surface (ADR-0279 §2), answered with 403; or where the act's
target does not exist. Otherwise the plan is commissioned (`plan.commissioned`), the act is
recorded as `administration.carried_out` naming the plan and the commissioner, with the act and
its target in the entry's digest, and the use case carries it out with the commissioner as its
actor, recording its own entry as it does by hand.

### 4. An update of Taktus is prepared as a plan and applies nothing

`instance.update` names a release. Its steps are a person's, from the guide *Upgrading*: a
backup moved off the machine, the upgrade one release at a time, and the check that the instance
is ready and every ledger verifies. If the upgrade fails, the release before comes back from the
backup without Taktus (section 5 of the guide). Commissioning records
`instance.update_commissioned` with the release and the commissioner, and applies nothing. A
person, or another instance, carries the steps out. `POST /administration/update` and
`taktusctl update prepare` open the draft; it is commissioned in the plan dialogue or with
`taktusctl update commission`.

## Alternatives

- **Each act through the run engine, as a run of a process.** The act is one call of a use case;
  a run would add a process version per act, and the right would be checked at a step instead of
  at the commission, where UC-10.2 asks for it.
- **An update the instance applies once commissioned.** That would administer the platform the
  instance runs on (ADR-0025), and put a version into production by the instance itself (ADR-0013
  D).
- **A generic act dispatcher that carries out every inventory act.** Some acts need a wider right
  than any identity holds, and some answer a key; carrying them out through a plan would widen a
  right or leak a key.

## Consequences

- `components/command/domain/model/planning.py`: `AdministrationPart`, `PlanDraft.administration`;
  `domain/service/guided.py` asks for its arguments.
- `composition/administration.py`: `IN_DIALOGUE`, `BY_HAND_ONLY`, `AdministrationPlans`;
  `composition/planning.py`, `composition/workspace.py`, the daemon's and the command line's
  wiring.
- `rest/planning.py`: `act` and `arguments` on `POST /plans`, 403 on commission;
  `rest/administration.py`: `POST /administration/update`; `cli/instance_command.py`: `update`.
- `web/src/routes/health`: the form that prepares an update.

## Where this promise ends

- The act is chosen by whoever opens the draft: the person, a form, or a chat that interprets what
  was said. How a sentence becomes an act is not decided here; the draft holds what was agreed
  (ADR-0237).
- Only the acts of section 1 are carried out as plans. The others stay by hand, each with its
  reason.
- Whether a person carried an update out is not recorded by Taktus. The health page shows the
  release the instance runs afterwards.
- A commissioned plan carries the act out once, at the commission. A plan due later does not
  wait for its date.
