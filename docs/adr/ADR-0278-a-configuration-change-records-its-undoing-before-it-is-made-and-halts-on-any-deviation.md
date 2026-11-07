# ADR-0278 — A configuration change records its undoing before it is made, and halts on any deviation

**Status:** accepted · extends ADR-0022, ADR-0024, ADR-0237 · UC-1.3, DEC-0228

## Context

UC-1.3 asks that, once a plan is commissioned, Taktus does the configuration work in the
organisation's own tools: projects and workflows in the ticket system, repositories, boards,
automations, webhooks. Every change is a connector action of a commissioned plan, recorded with
an egress entry naming the target and what changed (ADR-0022). Before a change is made, what
undoing it requires is recorded; a change whose undoing cannot be stated is handed to a person.
A deviation from the plan halts the configuration at the step boundary and is reported with the
options; Taktus never chooses a substitute. An action that cannot safely be repeated is never
repeated, also not after a restart (ADR-0024). The target is reached by capability, with the
credential of the identity on whose behalf the plan was commissioned.

## Decision

### 1. A change is a record of the commissioned plan

`Configure.prepare` takes the changes of a commissioned plan in their order, refusing a plan
that is not commissioned. A `ConfigurationChange` names the capability, the action, the read
that states the target's state before, the action that reverses it, what the output must hold
(`expects`), the kinds of record it may touch (`touches`), and the instruction a person follows
to make it by hand. It is made for the identity that commissioned the plan.

### 2. Each change at its own boundary, in five steps

1. The target's connector must declare the action as an outward operation. Otherwise the target
   cannot do what was planned: a deviation.
2. The identity's own credential for the capability is asked of `Credentials`. Without one the
   change is handed to the person, with its instruction.
3. The undoing is stated — the state before, read from the target, or the reversing action — and
   recorded, `configuration.undo_recorded`, in its own transaction before anything is sent. When
   neither can be stated, the change is handed to a person (`configuration.handed`).
4. The action is sent, with an idempotency key derived from the plan and the change. Its effect
   is recorded as `egress.write`, naming the capability as the adapter, the plan and the change,
   and the digest of what went out.
5. The output is held against `expects`, and every record the target reports against `touches`.
   A difference is a deviation.

### 3. A deviation halts and offers, never substitutes

A deviation sets the change to `deviated`, records `configuration.deviated`, and the
configuration answers with where it halted, why, and three options: change the plan and
commission it again, make the change by hand and let the configuration go on, or undo what was
configured from the recorded undoing. Carrying out the plan again halts at the same change until
a person acts. Carrying out an undoing in the target is a correction of what has left the
system, and a person's (ADR-0022 §3).

### 4. Never sent twice what the target cannot recognise

A change whose undoing was recorded and whose outcome was not may have been sent before a
restart. Where its operation's idempotency is `native` or `marked`, it is sent again under the
same key, and the target recognises the repeat. Where it is `none`, it is never sent again: it is
handed to a person to check the target (ADR-0024).

## Alternatives

- **Configuration as ordinary steps of a run.** The engine's steps do not record an undoing
  before acting, nor hold an output against what a plan expects; adding both to every step
  would burden every process with a configuration's rules.
- **An automatic undo on a deviation.** Undoing in a target system corrects what has left the
  system; ADR-0022 keeps it with a person.
- **The instance's own credential where the person has none.** UC-1.3 asks for the credential
  of the identity the plan was commissioned for; the instance's would act with rights the person
  may not hold.

## Consequences

- `components/command/domain/model/configuration.py`, `application/service/configure.py`
  (`Configure`, `Targets`, `Credentials`).
- Migration 0107: `configuration_change`.
- `tests/components/command/test_configure.py`.

## Where this promise ends

- Which changes a plan makes is the plan's: the person states the changes, their expected
  output and their undoing; Taktus does not derive them from a description.
- A person's own credential for a target is named per identity by the composition; an identity
  without one has its changes handed to it as instructions.
- The undoing is recorded and offered; it is carried out by a person.
- A tool without a connector is configured by a person from the instructions, as UC-1.3 bounds.
