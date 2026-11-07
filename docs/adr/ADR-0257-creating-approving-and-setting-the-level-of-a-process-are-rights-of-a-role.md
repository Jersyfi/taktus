# ADR-0257 — Creating, approving and setting the level of a process are rights of a role

**Status:** accepted · extends ADR-0131 §3 (rights per role) and ADR-0146 (a structure asked for
once it exists) · serves UC-7.3

## Context

UC-7.3 asks that creating a process, approving it for operation and setting or raising its
autonomy level are separate rights, each granted to roles. An act by an identity without the
right is refused and recorded with the right it lacked.

ADR-0131 built rights per role for a person's agent on the MCP surface. A right is one record per
role, so no right can be granted to a person outside a role. Registration asked for no right:
any identity the tenant knew could register a version, and any could approve a raise.

## Decision

### 1. Three rights of a process

The identity component's rights gain three:

- `process.create` — register the first version of a process the tenant does not have yet;
- `process.approve` — register a version, which approves it for operation, since the version
  registered last is the active one (ADR-0035);
- `autonomy.set` — set the level of a new process, or approve a version that raises one.

They are granted and withdrawn as every right is (`taktusctl identity grant`), and each grant is
a ledger entry.

### 2. Asked for once the tenant grants one

Registration asks for the rights once any role of the tenant holds one of the three. Until then
nothing is asked, as a person's step needs a role only once the tenant has a structure
(ADR-0146). From then on, the first version of a process needs `process.create` of whoever
registers it. Every version needs `process.approve` of whoever registers it. A first version,
or one that raises a level, needs `autonomy.set` of the approving person, or of whoever
registers where nobody approves. A raise still needs the quality history ADR-0039 asks for.

### 3. A refusal names the right

A version an identity lacks a right for is not stored. One `process.refused` per right lacked
records it, with the identity as actor and `lacks_` and the right as its outcome. The finding
names the identity, the act and the right.

## Alternatives

- **Every right asked for from the first day.** Every tenant that has no rights granted yet
  could register nothing, and the installation's first process would need an administrator's
  grant first. The tenant decides when its rights hold by granting the first one.
- **One right for all three acts.** The organisation could not separate who builds a process
  from who puts it into operation and who raises its level. UC-7.3 asks for the separation.
- **A lowered level as a right too.** Lowering a level makes a process safer. A rule lowers
  levels on its own (ADR-0110), and a person who lowers one is not held back.

## Consequences

- `identity/domain/model/identity.py`: `Right.PROCESS_CREATE`, `PROCESS_APPROVE`,
  `AUTONOMY_SET`; `IdentityDirectory.holds` and `granting`.
- `process/ports/rights.py`: `ProcessRights`; `RegisterProcessVersionHandler(rights=...)`.
- `tests/components/process/test_rights.py`.

## Where this promise ends

The rights hold for registering through `RegisterProcessVersionHandler`: the command line, the
HTTP surface and the planner all register through it. They do not hold for an act that does not
register a version: deactivating a process goes through its own path and is not asked yet.

A tenant that grants none of the three rights is asked for none. An identity proves itself as
the surface it acts on proves it. The command line names the acting identity by `--identity`
and holds the instance's state, so a person with the state can name anyone.
