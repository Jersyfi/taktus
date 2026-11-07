# NTC-0270 — The web design gate reads hyphenated routes, and `owner` holds the right to state the value basis

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-11-07
**Raised in:** branch `area/reporting` (release 1.0, concept mode, DEC-0228)
**How it follows:** CLAUDE.md §11 point 11 makes a hole in a gate's coverage met on the way a
finding, recorded where the gate changes. UC-9.1 §2 gives the setting of a target to "a person
with the right to steer the process"; ADR-0241 §2 and the shipped anchors give configuration of
a tenant to the person holding `owner`, and nothing yet names a narrower right to steer.

## 1. What was decided

- `tests/components/reporting/test_web_design_system.py` read the web app's route prefixes with
  the pattern `[a-z/]*`. A route with a hyphen, `/role-reports`, was read only up to the hyphen,
  so the gate checked a prefix that is no route. The pattern is now `[a-z/-]*`: it covers every
  route it covered before and the hyphenated ones besides. The gate is not weakened; it is
  widened.
- The value basis — personnel cost rates per role, the time by hand, the targets, the plan — is
  stated by a person holding `owner` (`PUT /value/basis`, ADR-0244 §2). That role is the right
  to steer a process until a right of that name exists.

## 2. The evidence

- `make gate-web` and `tests/components/reporting/test_web_design_system.py` pass with the page
  `/role-reports` (ADR-0178).
- `tests/adapters/rest/test_figures.py::test_the_value_basis_is_set_by_owner_and_its_figures_say_who_set_it_when`.

## 3. What was considered

- **Renaming the route without a hyphen.** Rejected: the gate would still miss the next one.
- **A right `steer` per process for targets.** Not built: no right of that name exists in the
  identity component, and inventing it is beyond this area. `owner` is the narrowest existing
  holder of tenant configuration.

## 4. Which entry permits it

M2.6. The owner may overrule it in the pull request.

## 5. The entry it proposes

None beyond M2.6: a gate widened to the routes it was meant to read is a finding fixed on the
way (CLAUDE.md §11), and tenant configuration by `owner` follows ADR-0241 §2.
