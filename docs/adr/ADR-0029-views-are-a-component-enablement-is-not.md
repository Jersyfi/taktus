# ADR-0029 — Views are a component; enablement is not

**Status:** accepted · amends ADR-0016: a twelfth component, `reporting`

## Context
The use cases are filed by component: someone working on accounting finds the requirements where
they find the code. Two groups of the original project definition fit no component.

**Reporting and transparency** (epic E6 of the definition) is the activity log, reports on demand
and on a schedule, the takeover test, role-based views, Taktus explaining its own actions, and
the proof of value. The activity log is the ledger's. The figures behind a proof of value are
the value ledger's. But a *view* — what a management role sees, what an employee sees, which
figures appear together, how deep a reader may drill — belongs to neither. Splitting E6 between
`ledger` and `value` would put the rule "every role sees what it is entitled to see" in two
places, and principle 7 forbids exactly the result: two numbers for the same thing.

**Enablement** (epic E13) is a guided and an expert mode, method scaffolds, an automation coach,
joy in daily use, and making a person's own contribution visible. It is real product
substance, promised by principle 14. It fits no component because it is about how a person
experiences the system, not about data the system owns.

A bounded context is a part of the domain with its own language and its own rules. The question
for each group is whether it has both.

## Decision

**1. `reporting` is a component.** It owns the *reader's side*: views and who may see them,
reports and when they are delivered to whom, and the explanation of an action given on request.
Its language is its own — a view, a reader role, a report, a schedule, a drill-down, a delivery
— and so are its rules: principle 7 (every role sees what it is entitled to, and no figure
exists only in one view), principle 9 (no report without a reader), and principle 14 (no view
of a named person; aggregation by role or department only).

**It owns no figure.** Every number it shows is owned by the component that produces it: the
activity log by `ledger`, consumption and the Takt by `accounting`, the value ledger by `value`,
blocked time by `run`. `reporting` reads them — reading across a component boundary is allowed
(ADR-0016) — and composes them. A figure defined in `reporting` is a second definition and is
refused in review; that is how principle 7's "no two numbers for the same thing" holds.

The use cases of E6 are filed as follows:

| Definition | What | Component |
|---|---|---|
| UC-6.1 | the complete activity log | `ledger` |
| UC-6.2 | reports on demand and on a schedule | `reporting` |
| UC-6.3 | the takeover test: a person can run a process without Taktus | `process` — the instructions are part of the process version (ADR-0013 B) |
| UC-6.4 | role-based views | `reporting` |
| UC-6.5 | Taktus explains its actions | `reporting` |
| UC-6.6 | the proof of value | `value` for the figures; the view is `reporting`'s, filed with the figures |
| UC-6.7 | the bus-factor index | `value` — a figure computed from takeover and removal test results; the views show it |
| UC-6.8 | incident and incident report | `governance` for the incident; the report is an artifact of the incident |
| UC-6.9 | the exactness statement | `process` — it is generated from the process version |

**2. Enablement is not a component.** It has no data of its own and no rule of its own that is
not already another component's. Taken apart, each E13 use case is a requirement on something
that exists:

| Definition | What | Component |
|---|---|---|
| UC-13.1 | a guided and an expert mode that reach the same result | `command` — the dialogue in which a person says what they want is command's; the web app and the channels present it |
| UC-13.2 | method scaffolds for typical projects | `catalog` — a scaffold is a blueprint |
| UC-13.3 | the automation coach | `command` — a proposal to the person, from what they asked for before |
| UC-13.4 | visible small successes, a personal dashboard | `reporting` — a view |
| UC-13.5 | making a person's own contribution visible, never surveillance | `reporting` — a view that belongs to the person |
| UC-10.3 | usability for people who are not technical | `command` — guided onboarding is the guided mode's first use |

A component named `enablement` would own nothing and would have to reach into `command` and
`reporting` for everything it does. That is the shape of a feature, not of a bounded context.

**Enablement is kept findable as a whole.** Every use case of E13 carries `epic: E13` in its
front matter, and principle 14 must be served by at least one of them: `make gate-vision` fails
on a principle nothing serves. Scattering is what happens when nobody decided; here the placement
is decided, and the group is one query away.

**3. The package arrives with its first implementation.** `src/taktus/components/reporting/`
is created by the pull request that builds the first `reporting` use case, together with its
`import-linter` independence contract and its line in `tests/architecture`. Until then
`docs/architecture/project-structure.md` lists the component and says it has no package yet.
Creating an empty package now would put an implementation path beside use cases written in the
same change, which the use case rule forbids (CLAUDE.md §9).

## Alternatives
- **E6 across `ledger` and `value`.** Rejected: the rule about who sees what would live in two
  places, and a view combining a ledger figure with a value figure would belong to neither.
- **Views as a driving-adapter concern, in the web app only.** Rejected: views are delivered
  through channels and reports as well as the web app, and the visibility rules of principles 7
  and 14 must hold on every path. Rules that hold on every path belong in the core.
- **An `enablement` component.** Rejected for the reason in §2: it would own nothing.
- **A folder `docs/usecases/enablement/` outside the component rule.** Rejected: the use case
  layer is filed by component so that requirements sit beside their code; one exception makes
  the rule a suggestion. The `epic` field gives the same view without the exception.

## Consequences
- `docs/architecture/project-structure.md` lists twelve components; ADR-0016's list gains
  `reporting`.
- A figure has one owner. A pull request that computes a figure inside `reporting` is a finding.
- The E13 use cases are written in `command`, `catalog` and `reporting` in the migration's third
  and fourth steps, each with `epic: E13`.

## Where this promise ends

`reporting` owns no figure by discipline and by review, not by a gate: nothing yet detects a
computation inside a view that should have been read from its owner. The package and its
architecture contract do not exist until the first `reporting` use case is built, so until then
the boundary is a line in a document. The placement of the E6 and E13 use cases in the tables
above is where they are filed; it decides nothing about what each requires, which is the owner's
(M3.15) and is written when each is migrated. Keeping enablement findable rests on the `epic`
field being set, which the use case gate checks for presence where it is given and cannot check
for a use case that should carry it and does not.
