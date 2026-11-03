# NTC-0254 — UC-7.11: departments share the runners fairly and hold their quotas

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-31
**Raised in:** branch `concept/package-c--units` (package C, concept mode, DEC-0222)
**How it follows:** the owner accepted the DevOps review of 2026-10-12 (DEC-0187), which filed issue #343 for `0.7.0`: a job carries the organisational unit it runs for, the runners share places fairly between units, and a tenant may set quotas per unit, concurrent runs and budget, never per person. No use case required it: UC-1.4 names the structure and UC-8.5 budgets inherited along it, neither a share of the runners. UC-7.11 states #343 as a requirement. Where the issue left a reading open, the stricter one in substance was taken, as CLAUDE.md §8 asks.

## 1. What was decided

UC-7.11, *Departments share the runners fairly and hold their quotas*, component `governance`,
version `0.7.0`, the next free number of its area (`docs/usecases/NUMBERING.md`). Its conditions
are those of #343. Three readings were settled, and ADR-0166 builds them:

- **The unit is the department.** The first level below the tenant in the command's
  `org_path`, because the issue and its measurement speak of departments. Teams and projects
  share their department's places.
- **The budget quota holds what runs commit, not what they spent.** A run commits its whole
  budget to its unit's month when it starts. This never lets a run start that the unit's
  remaining money cannot hold; a reading of what was spent would.
- **A run whose budget names no amount in the quota's currency halts for a person.** It cannot
  be counted against the quota, and letting it through would make the quota a limit only for
  the runs that state their money.

## 2. The evidence

- Issue #343, *What must be achieved*, *How it is verified* and *Where the boundary lies*;
  DEC-0187; `docs/research/2026-10-12-devops-review.md` §T3.
- UC-1.4 §2, UC-8.5 §2, ADR-0005, ADR-0020, ADR-0043; principle 14.

## 3. What was considered

- **Amending UC-8.5.** Rejected: UC-8.5 is cost control with alerts and forecasts; a share of
  the runners is neither, and UC-8.5 keeps its state.
- **A unit at every level of the structure.** Not taken for this step: quotas on several levels
  need the inheritance rules of UC-8.5, which are not built.
- **A budget measured from consumption.** Rejected for the reason above.

## 4. Which entry permits it

M2.7, *bringing a use case up to what the owner has already accepted*: here the issue the owner
accepted with the DevOps review. The owner may veto it within seven days of the pull request.
