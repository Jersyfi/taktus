# NTC-0271 — A person's stop is reported to the role `operator` unless the tenant names another

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-11-07
**Raised in:** branch `area/governance2` (release 1.0, concept mode, DEC-0228)
**How it follows:** UC-7.2 §1 says a stop "is followed by a situation package to the on-call
role". No source names that role for a tenant that configured nothing. The shipped watch
configuration already gives every other watch value a default the tenant may change (NTC-0212,
NTC-0226, NTC-0228). The precedent applies: the on-call role is one more value of it. Strict in
substance, sparing in ceremony: the incident is always raised, and the role only says to whom.

## 1. What was decided

`WatchConfiguration.on_call` names the role a person's stop is reported to (ADR-0280 §1). Its
shipped default is `operator`, the role of whoever runs the instance in `docs/vision/personas.md`.
`taktusctl incident configure --on-call ROLE` names another. A role, never a person
(principle 14).

## 2. The evidence

- `tests/components/governance/test_stop_incident.py`: a confirmed stop by a person raises one
  incident addressed to the configured role, and to `operator` where none is configured.

## 3. What was considered

- **No default, and no incident until a role is configured.** Rejected: a stop must always be
  followed by an incident (UC-7.2 §1). A missing configuration would silently drop it.
- **The role of the person who stopped.** Rejected: that person already knows. The package is
  for whoever must look after the stop.

## 4. Which entry permits it

M2.6, with NTC-0212 as precedent. The owner may overrule it in the pull request.

## 5. The entry it proposes

None beyond NTC-0212's M1.24, *the shipped default of a tenant setting that limits no
spending*: the on-call role is one more such setting.
