# ADR-0146 — A human step and a fallback to a person name a role, never a person

**Status:** accepted · extends ADR-0004 (method choice), ADR-0008 (anchors name a role), ADR-0015 (no figure assesses a named person) and ADR-0018 (wait and human produce no result) · issue #331, UC-4.20

## Context

A `human` step says that a person does the work. A `fallback` with `to: human` says that a
person takes the step over when its method is not good enough. Neither says **which** person.
The process alone cannot tell who has to act.

Roles exist elsewhere already. An anchor names the role that decides (`Anchor.json`). A check of
kind `approval` or `sampling` names the role that checks (`Check.json`). An identity holds roles,
and a right is granted to a role, never to a person (UC-7.3). The person behind a role is
resolved when it is needed.

Three readers need the role on the step itself. The bus-factor index counts a role "where a
process's takeover instructions require it" (UC-6.7); today that is free text. The value balance
of a process needs "the roles needed" to revert it (UC-9.3). The value-chain view (#338) and the
role profiles (#344) group steps by role.

A **structure** below means the roles a tenant's identities hold. A tenant without any role
held has no structure yet.

## Decision

### 1. The shared kernel's `Step` and `Fallback` gain `role` and `expertise`

Both are optional in `contracts/shared/v1/Step.json`, so that every step written before stays
valid.

- `role` names a role of the tenant's structure. It has the pattern of a check's role:
  lowercase, digits and hyphens. It never names a person.
- `expertise` lists what the work needs a person to know, as short phrases. It is optional and
  needs `role`.
- A step carries `role` and `expertise` only when its method is `human`.
- A fallback carries them only when its `to` is `human`.

The schema states these rules in its `allOf`. The Python binding states the same rules in the
same order.

### 2. Registration refuses a human step without a role once the tenant has a structure

Registration asks the identity component which roles the tenant's identities hold. While none
is held, a human step without a role is registered as before: a tenant that has not set up its
structure is not stopped from starting.

Once a role is held, registration refuses, naming every finding:

- a `human` step without a role;
- a fallback to a person without a role;
- a role that no identity of the tenant holds.

The refusal is `InvalidProcess`, like every other finding of registration. Nothing is written
to the ledger, because nothing was attempted that a person must later account for.

### 3. The live representation shows the role

The process level of UC-6.10 shows, for each step, its role and the expertise it needs. For a
fallback to a person it shows the fallback's role. The text equivalent says it in words. No
level shows the person who holds a role.

## Alternatives

- **A required role in the schema.** Rejected: every bundle written before would become
  invalid, and a tenant that has not defined its structure could register nothing.
- **A person's identifier on the step.** Rejected: principle 14 and UC-7.3. A person leaves or
  is absent; a role stays.
- **Expertise as free text in the takeover instructions.** Rejected as the only place: a
  reader that counts or groups by expertise cannot read prose. The takeover instructions may
  still explain it.
- **Refusing an unknown role only with a warning.** Rejected: a role nobody holds means that
  nobody is asked. That is the gap this record closes.

## Consequences

- `contracts/shared/v1/Step.json`, its README row, and examples valid and invalid.
- `taktus.shared.v1.step`: `Step.role`, `Step.expertise`, `Fallback.role`,
  `Fallback.expertise`, with the rules of §1.
- The process component's port `RoleStructure`. The composition root answers it from the
  identity component's `role_holders`.
- The reporting component's process level carries `role`, `expertise` and `fallback_role`. The
  web app shows them.

## Where this promise ends

- **No resolution at run time yet.** A run that waits on a human step does not yet address the
  wait to the step's role. The wait is shown to whoever may see the run, as before. Addressing
  it to the role follows the decision request's resolution (ADR-0042) and is a later change.
- **No check of expertise.** Nothing checks that a person of the role has the expertise. It is
  a statement for the reader, never a filter on people.
- **No role for other methods.** A `worker`, `llm` or any other step names no role. An
  anchor and a check keep naming theirs as before.
- **Versions registered before are read as they are.** A version stored without a role is not
  refused later, when the tenant gains a structure. It is refused only when it is registered
  again.
