# ADR-0275 — The organisation's structure is a tree of named levels, and what a unit holds is seen, shared and paid for there

**Status:** accepted · extends ADR-0020, ADR-0055, ADR-0166 · UC-1.4, DEC-0228

## Context

UC-1.4 asks for the organisation's structure as a tree whose levels the organisation names.
Every process, run, agent, shared connector and budget belongs to exactly one unit of it.
Visibility, sharing and the attribution of cost follow the unit: moving a process from one team
to another moves all three, and nothing else is configured.

Until now the tenant was the only boundary. An identity carried an organisational path
(`org_path`), and a run carried the department of its command's path as `org_unit` (ADR-0166).
No record said which units exist, and no record placed a process in one. The one visibility
predicate (`reporting/domain/service/visibility.py`, ADR-0055 §5) compared tenants only.

## Decision

### 1. The structure is the identity component's

The identity component owns tenants, accounts and the organisation's structure
(`components/identity/__init__.py`). Four records:

- **`OrgStructure`**, one per tenant: the names of its levels, the root's first. Until the
  organisation names its own, they are `tenant, department, team, project`.
- **`StructureUnit`**, one per unit: its identifier, name, level and parent. The root's
  identifier is the tenant's and exists without being added. A unit is added one level below its
  parent and never below the last level.
- **`Placement`**, one per placed object, identified by `<kind>:<object>`: a process, a shared
  agent, a connector, a model, a skill or a budget in one unit. An object has one placement by
  construction. An object nobody placed is in the root.
- **`Filing`** and **`KnowledgeHome`**, for where things are documented (§6).

### 2. A run is in its process's unit, from its creation on

When the engine creates a run, it asks the structure where the run's process is placed
(`OrgUnits.placed`) and sets `Run.org_unit` to that unit. Where nobody placed the process, the
command's unit stays, as ADR-0166 set it. A run keeps its unit: a process moved later moves its
next runs, never what a run already consumed. The unit's quotas of ADR-0166 hold the run under
that unit's identifier.

### 3. An identity belongs to the units of its path and to those that name it

An identity belongs to every unit its organisational path names and to every unit that names it
as a member. Its **default context** is every unit it belongs to that is not inside a private
unit (ADR-0276), and the root.

### 4. A reader sees what is placed in its context and above it

A reader sees an object placed in a unit of its context, or in a unit above one. It does not
see what is placed in a sibling unit, nor below. The identity component computes, where it
forms a `Resolution`, the processes the reader does not see (`Resolution.unseen`). The reader of
the live representation carries them (`Reader.unseen`), and the one predicate refuses a process,
its runs and their count when the process is among them. Where nothing is placed the list is
empty, and the tenant's boundary alone holds, as before. Every channel path forms its reader
through the same answer (`ports/identity.Sight`), so that no path is wider than another.

### 5. What a unit shares, its units below use

A shared agent, connector, model or skill placed in a unit is used by the processes of that
unit and of every unit below it (`usable_by`). What the root holds, every process uses.

### 6. Cost counts in the unit and above it

A run's consumption counts in its unit and in every unit above it (`figures`). A private unit
stops the counting: its consumption is in no figure above it (ADR-0276).

### 7. Where a thing is documented is recorded once, with its link

For anything Taktus set up, the structure files where it is documented: every place, each with
the link that opens it (`file`, `where`). Where the organisation configured a knowledge system
for the unit or a unit above it (`KnowledgeHome`), the place is that system, under the
configured base link, and nothing is kept inside Taktus beside it. Taktus's own page is the place
only where no unit on the path configured one.

### 8. Every act on the structure is an administrative act in the ledger

Naming the levels, adding a unit, placing or moving an object, configuring a knowledge system
and filing are each a ledger entry naming the identity that did it, in the same transaction
(`structure.levels_named`, `structure.unit_added`, `structure.placed`, `structure.moved`,
`structure.knowledge_configured`, `structure.filed`). The target is carried by the entry's
digest, as every identity act's is (ADR-0040). Shaping the structure is an administrative act
under the right `structure.shape` (UC-10.2).

## Alternatives

- **Visibility per role (UC-6.4) first.** Roles say what a person may do; the structure says
  where a thing lives. UC-1.4 asks for the second, and the predicate keeps room for the first.
- **A run attributed by its process's placement at reading time.** A moved process would carry
  its old runs' consumption with it, and a month's figure would change after the month.
- **A copy of the documentation inside Taktus beside the knowledge system.** Principle 1 forbids
  a second system of record; two copies drift apart.
- **A separate database per unit.** ADR-0020 leaves that to the organisation's choice of
  tenants; a unit inside a tenant is a record, not a database.

## Consequences

- `components/identity/domain/model/structure.py`, `domain/service/structure.py`,
  `application/service/structure.py` (`OrganisationStructure`).
- `Resolution.unseen`, `Reader.unseen`, `ports/identity.Sight`; the predicate reads them.
- `OrgUnits.placed`; `ExecuteRun` sets a run's unit from it.
- Migration 0107: `org_structure`, `structure_unit`, `placement`, `filing`, `knowledge_home`.
- `taktusctl structure`, the HTTP surface's `/structure`, the web app's *Structure* page.
- `tests/components/identity/test_structure.py`,
  `tests/components/run/test_structure_attribution.py`.

## Where this promise ends

- A reader's context is its default context. Reading inside one project's context is asked of
  the structure by name (`unseen(..., within=)`); the live representation reads the default.
- The predicate hides processes and their runs. A record that names no process — an incident, a
  finding, a report to the owner — is not narrowed by the structure here.
- A unit's quota is its own: a department's quota does not hold its teams' runs.
- Moving a process does not move its open runs, its recorded consumption or its documentation's
  place; filing again records the new place.
- The structure does not grant rights. Who may do what stays UC-7.3's.
