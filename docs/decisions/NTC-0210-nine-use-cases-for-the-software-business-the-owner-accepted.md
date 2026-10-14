# NTC-0210 — Nine use cases for the software business the owner accepted

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-14
**Raised in:** the pull request that records DEC-0199
**How it follows:** the owner accepted on 2026-10-14 that Taktus fully supports a software business's catalogue of use cases by `1.0.0`, with its introduction path (DEC-0199). The catalogue lists thirteen requirements on the tool that carries it, a rule for rising and falling between autonomy stages, a path in six stages and a list of what stays with a person. Nine of these are required by no use case yet. Each new use case below states one of them as a condition, and adds nothing the catalogue does not ask for; where the catalogue meets a principle, the principle bounds it.

## 1. What was decided

Nine function-level use cases are written, each in state `specified`:

| Use case | Follows from the catalogue's | Version |
|---|---|---|
| UC-4.16 An expected run that does not happen is an incident | requirement 5, heartbeat and dead man's switch | `0.4.0` |
| UC-4.17 Deadlines and response limits are rules of the process | requirement 10 | `0.5.0` |
| UC-4.18 A change is held to its evaluation cases, and drift is measured | the evaluation use cases on change, drift and a growing set | `0.5.0` |
| UC-6.13 Signals against corridors, and a daily report of only what deviates | requirements 11 and 12; the daily report | `0.4.0` |
| UC-7.5 Corrections are counted, and a level falls by rule | requirement 2; the rule for rising and falling | `0.4.0` |
| UC-7.6 An outward message is labelled, checked independently, and held | the sending, scoring, independent-check and AI-label use cases; promises and mass sending on the list of what stays with a person | `0.6.0` |
| UC-7.7 A step sees only the data of its case | requirement 9; user data on the list | `0.5.0` |
| UC-8.12 A cap on open work, and a stop to repetition | the use cases on open work and on repetition | `0.5.0` |
| UC-9.6 Introduced into a running operation in stages | the path in six stages | `0.5.0` |

The blueprint-level case UC-03, `docs/usecases/AF-03-software-operations.md`, maps all 96 use
cases of the catalogue to processes and these use cases.

## 2. The evidence

- DEC-0199, the owner's answer and how the session reads it.
- For each requirement of the catalogue, the existing use cases were checked first (UC-03 §7).
  Where one already required it — approval as a state, agents as actors, budgets per agent,
  evidence over claims, intake from every source, the border to neighbouring systems — no use
  case was written.
- A stop per adapter with a confirmation goes beyond UC-7.2's scopes. It is a small amendment
  and is left to an issue of its own, so that UC-7.2 is changed in one place.

## 3. What was considered

- **One use case for all thirteen requirements.** Rejected: each requirement belongs to a
  different component, and a use case lives with its component (`docs/usecases/README.md`).
- **Amending UC-7.1 for corrections and the fall by rule.** Rejected: UC-7.1 is about the range
  and the raise; the fall by rule and the counting are a requirement of their own with tests of
  their own.
- **A learned pattern of a person for the audit of privileged actions.** Rejected: principle 14
  forbids a skill containing a person's behavioural pattern. UC-03 B-5.04 uses a rule over an
  organisation-wide time window instead.
- **Placing every new use case at `1.0.0`.** Rejected: the stages of UC-03 open from `0.4.0`, and
  each use case is placed at the milestone of the first stage that needs it.

## 4. Which entry permits it

M2.7, *bringing a use case up to what the owner has already accepted*: here a feature the owner
accepted (M3.2) in DEC-0199. The owner may veto any of the nine within seven days of the pull
request that carries them; a veto turns it into a request under M3.15.
