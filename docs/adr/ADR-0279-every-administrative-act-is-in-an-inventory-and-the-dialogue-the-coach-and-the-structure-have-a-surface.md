# ADR-0279 — Every administrative act is in an inventory, and the dialogue, the coach and the structure have a surface

**Status:** accepted · extends ADR-0237, ADR-0238, ADR-0240, ADR-0275 to ADR-0277 · UC-10.2,
UC-1.2, UC-13.1, UC-13.3, UC-10.3, DEC-0228

## Context

UC-10.2 asks that every administrative act is available through the command line and through
the web app, and that a test takes the list of administrative acts and finds each in both. Until
now the identity and quota acts existed on the command line only, and no list named the acts.

UC-1.2, UC-13.1 and UC-13.3 were built as records and rules (ADR-0237, ADR-0238, ADR-0240), but no
surface presented them: a person could not reach the plan dialogue, its guided questions or their
coach. UC-10.3's guided start is the guided mode's first use, in the web app.

## Decision

### 1. One inventory of administrative acts

`adapters/driving/inventory.py` names every administrative act once: what it does, the command
line's command, the HTTP surface's operation the web app calls, and the web app's page. The web
app marks the act's form or list with `data-act="<act>"`.
`tests/adapters/test_administration_inventory.py` walks the inventory and finds each act's command,
its operation in `api/openapi.yaml`, its page and its mark. An act on one way in and not on the
other fails the test.

### 2. The tenant's administration on the HTTP surface needs a right

`/administration/identities`, `/administration/links`, `/administration/rights` and
`/administration/units` call the same use cases the command line calls, so each act is the same
ledger entry by either way in. They need an account key, or the web app's session, of an
identity whose roles hold the right `tenant.administer`; the command line authenticates by holding
the instance's state, as before. Shaping the structure needs `structure.shape` (ADR-0275 §8).
The tenants themselves stay with the instance's administration key (ADR-0104).

### 3. The plan dialogue's surface: `/plans`

A person opens a draft for what they said, reads it as the guided or the expert mode shows it,
answers the guided question or sets the fields, and commissions the current version. A guided
answer that chooses a template names a process version, whose steps the draft takes (the
composition's `PlanActs`, because it crosses the command and process components). The guided
mode accepts autonomy level 1 or 2 only (ADR-0026). The mode is a value the read passes; the web
app keeps the reader's choice for the visit and stores it nowhere, and nothing on the surface
reads it to decide what a person may do (ADR-0238 §4).

### 4. The coach's surface: `/coach`

A person reads their own coach — their hints, their settings with the default stated, their own
share of lasting automations — sets it, and dismisses or accepts a hint. Every call reads only the
caller's own; there is no operation that names another person (ADR-0240).

### 5. The structure's surface: `/structure`, `/projects`, `/sessions`

The structure as the reader may see it — no private project but their own, no placement of a
process their context does not see — shaping it, where something is documented, the reader's
projects, and the reader's session in one (ADR-0275 to ADR-0277).

### 6. Four pages of the web app

`#/plans` (the guided start and the plan dialogue), `#/coach`, `#/structure` (with projects and
the session) and `#/administration`, each drawn on the design system's tokens and reached from the
one navigation list (ADR-0178). The register shows each adapter's maturity as the catalogue
records it, never settable (UC-8.9).

## Alternatives

- **A generic administration endpoint that dispatches by act name.** It would hide each act's
  shape from the interface's description, and the web app would have to know them anyway.
- **The inventory as a document.** A list only a reader reads drifts from the code; a list a test
  walks cannot.
- **The mode stored per person.** A stored mode would invite reading it; the web app keeps
  nothing in the browser but its theme (ADR-0177 §3).

## Consequences

- `adapters/driving/inventory.py`, `rest/administration.py`, `rest/planning.py`,
  `rest/structure.py`, `cli/structure_command.py`; `composition/planning.py`,
  `composition/workspace.py`; `Right.ADMINISTER`.
- `web/src/routes/{plans,coach,structure,administration}`, their views, `web/src/lib/workspace.ts`.
- `tests/adapters/test_administration_inventory.py`, `tests/adapters/rest/test_planning.py`,
  `tests/adapters/rest/test_structure_and_administration.py`, `web/src/lib/workspace.test.ts`.

## Where this promise ends

- The inventory holds the acts that exist in both ways in. A tenant's export and import, the
  backup's listing on the command line, the instance's health and an update commissioned in
  dialogue are not in it yet; UC-10.2 names them, and they are its open work.
- An administrative act asked of Taktus in dialogue is not yet carried out as a plan; UC-10.2's
  second condition is open.
- The chat presents neither the guided questions nor the coach's hints; the web app does.
- The web app's pages are tested as they render; their use by people who are not technical is
  UC-10.3's trial, which only people can give.
