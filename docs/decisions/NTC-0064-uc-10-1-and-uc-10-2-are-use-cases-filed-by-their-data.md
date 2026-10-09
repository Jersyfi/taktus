# NTC-0064 — UC-10.1 and UC-10.2 are use cases, filed by their data

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-09
**Raised in:** [#136](https://github.com/Jersyfi/taktus/pull/136)
**How it follows:** ADR-0029 files a requirement with the component whose data and rules it concerns, so that someone working on that component finds it beside the code; `docs/architecture/project-structure.md` §1 names what each component owns. The definition states UC-10.1 and UC-10.2 as requirements with acceptance criteria, and `docs/usecases/README.md` holds a requirement to a verifiable condition, which an architecture decision does not give: an ADR says how something is built, not that it must hold. Between "carried by architecture" and "a use case", the stricter in substance is the use case; deciding its folder by the rule ADR-0029 already applies, with a notice rather than a request, is the option with less ceremony.

## 1. What was decided

Two numbers of the definition that no step of the migration had filed, and one number filed differently
from the migration's plan:

- **UC-10.1, runs anywhere on any hardware**, is a use case in `governance`, which holds the capacity
  report of the platform an instance runs on (ADR-0031) and the rule where an instance may run
  (ADR-0025).
- **UC-10.2, administration**, is a use case in `identity`, which owns tenants, accounts, the
  organisation's structure, channel identity and roles — most of what the definition lists. The rest is
  pointed to where it lives: maturity in `catalog`, rights in `governance`.
- **UC-9.5, bottleneck and waiting analysis**, is filed in `accounting`, which owns forecasts and
  marginal value, and not in `value` with the rest of E9. The analysis is the marginal value of a
  higher limit (ADR-0015); the blocked-time accounts it reads are `run`'s.

What the three require beyond the definition is asked in DEC-0087 like every other condition of the
step; their placement is not.

## 2. The evidence

- `docs/architecture/project-structure.md` §1: `identity` — tenants, accounts, org structure, channel
  identity, roles; `accounting` — consumption capture, Takt, forecasts, marginal value; `value` — value
  ledger, cost and benefit entries, revert analysis. The `governance` package states that it holds the
  capacity report.
- The migration's working file left UC-10.1 and UC-10.2 open: "step 4 settles whether each is a use
  case and where, or is carried by architecture". It filed E9 in `value` without naming UC-9.5's data.
- UC-8.3, UC-10.3 and UC-11.1 already point at definition `UC-10.1` as the place for installation and
  environments; without a use case those pointers would end in nothing.

## 3. What was considered

- **Carried by architecture, no use case.** Rejected for both: ADR-0013, ADR-0020 and ADR-0025 say how
  an instance runs, not that a private person installs it with one command or that features are the
  same in every variant; nothing would check either. The migration did keep `UC-5.4` as architecture,
  because its verification already exists as the connector contract's conformance suite; UC-10.1 and
  UC-10.2 have none.
- **A folder outside the component rule.** Rejected for the reason ADR-0029 gives: one exception makes
  the rule a suggestion.
- **UC-9.5 in `value`, as planned.** Rejected: the figure it produces, marginal value, is owned by
  `accounting`; filing the requirement elsewhere separates it from its code.

## 4. Which entry permits it

None of mode 2 names where a use case of the definition is filed when the migration's plan does not
say it or says it against a component's ownership; M3.15 is about what a use case requires, not its
folder, and M1.10 about how it is described. M2.6 applies: decided in the direction of ADR-0029.

## 5. The entry it proposes

**M1.12** — *Where a use case is filed*: the component whose data and rules it concerns, as ADR-0029
decides for reporting and enablement; recorded in the use case's front matter. Mode 1 rather than 2,
because the placement follows from ADR-0029 and `docs/architecture/project-structure.md` §1 without
judgement, and changes nothing a use case requires.
