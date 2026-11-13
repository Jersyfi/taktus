# NTC-0283 — Staff, partnerships and its own limits are strategic anchors of the software-operations blueprint

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-11-13
**Raised in:** branch `area/ops2` (final round before 1.0, concept mode, DEC-0236)
**How it follows:** UC-03 §6 keeps "staff and partnerships" with a person as a strategic anchor.
It also keeps "its own limits: guardrails, budgets and autonomy levels". UC-03 §9 asks that a
test runs a level-4 process into each row and finds it halted. `blueprint.yaml` already lists
both as strategic anchors. `anchors.json`, the configuration a tenant takes, held only money,
legal acts and corrections. Writing the two rows into it brings the proposal up to what UC-03
already requires; it adds no requirement.

## 1. What was decided

`blueprints/software-operations/anchors.json` gains two strategic anchors:

- `anc-staff` on the actions `staff.*` and `partnerships.*`;
- `anc-limits` on the actions `orchestrator.limits.*`, `orchestrator.levels.*` and
  `orchestrator.guardrails.*`.

No connector serves those acts today. A process cannot change a limit or a level, because no
capability exposes one, and a raise needs a person's approval at registration (ADR-0039). The
anchors therefore hold the first such act a connector adds. `payment.refund.create` already
stands for moving money the same way. Reading what the instance spent (`orchestrator.spend`)
is not anchored.

The other rows of §6 are held by every run's frame, not by `anchors.json`. Promises and mass
sending are held by the message frame (UC-7.6). User data outside a case is held by the case
scope (UC-7.7).

## 2. The evidence

`tests/governance/test_software_operations_anchors.py` runs a level-4 process into each of the
following rows and finds it halted with a decision request:

- staff and partnerships;
- its own limits and levels;
- promises;
- mass sending;
- user data outside a case;
- moving money and corrections, which it already covered.

## 3. What was considered

- **Leaving the rows to a tenant's own anchors.** Rejected. UC-03 §6 says Taktus never runs
  with less than this list. The shipped proposal is the floor a tenant takes over.
- **A legal class for staff.** Rejected. UC-03 §6 names it a strategic anchor. The legal acts
  within it, such as signing a contract, are acts under `legal.*` and held by `anc-legal`.

## 4. Which entry permits it

M2.6. It is not M2.7: that entry brings a use case up to what the owner accepted, and here the
use case already requires it; the blueprint's configuration is brought up to the use case. The
owner may overrule it in the pull request.

## 5. The entry it proposes

M2.7, widened to a shipped configuration brought up to a use case it serves: the same
restoration, one layer further down.
