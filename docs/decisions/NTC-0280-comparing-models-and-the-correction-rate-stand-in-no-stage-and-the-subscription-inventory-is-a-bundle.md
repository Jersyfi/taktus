# NTC-0280 — Comparing models and the correction rate stand in no stage, and the subscription inventory is a bundle

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-11-13
**Raised in:** branch `area/ops1` (final round before 1.0, concept mode, DEC-0222), for issue
#437
**How it follows:** ADR-0191 §1 opens a stage only once every process it adds runs, and §4
took B-9.01 out of the stages' lists because the instance raises the daily report, so no
tenant can register it. NTC-0266 says B-2.05 is the model trial of UC-8.14 and needs no bundle;
NTC-0263 says B-4.03 is UC-7.5's count per process and action. Both are served by the instance,
like B-9.01, so ADR-0191 §4's precedent applies to them. B-2.06 has a source for half its row:
the billing export B-1.01 and B-1.12 read states what each service cost. DEC-0225 says to build
what a published interface serves and to name the rest as a limit. Strict in substance,
sparing in ceremony: the stage counts only what a tenant can run, and nothing is faked.

## 1. What was decided

- `blueprints/software-operations/stages.yaml` no longer names `b-2-05` (stage 1) or `b-4-03`
  (stage 2). Its header says where each is served. A row served inside another process's bundle
  stays named, as NTC-0263 decided.
- **B-2.06** is the bundle `processes/B-2.06-subscription-inventory.yaml`, version 1, level 2:
  every quarter the billing export's 91 days are summed per service by the statistic `total`
  (`exact`), and the list is filed as one issue after a person confirmed it, once while one is
  open. Its limits are named in the bundle and the README: a subscription's real use, which no
  source states; subscriptions billed outside the cloud; and the proposal to cancel or build
  in-house, which without the use would be a guess and so stays with the person.
- With both, every process stage 1 names has a shipped bundle: a tenant can declare stages 0
  and 1 as shipped and open them.

## 2. The evidence

- `tests/governance/test_stages_shipped.py`: stages 0 to 2 name only processes a shipped bundle
  serves, except the rows NTC-0263 and NTC-0266 place in B-3.02 and the document B-4.07; each
  stage's shipped condition, met, opens the next, and missed in one figure keeps it closed.
- `tests/governance/test_stages.py`: 85 processes of UC-03 §4.1 to §4.10 stand in a stage, and
  neither `b-2-05` nor `b-4-03` does.
- `tests/composition/test_software_operations_ops.py`: B-2.06 sums the quarter per service and
  files the inventory once.

## 3. What was considered

- **A bundle for B-2.05 that starts a trial.** Rejected by NTC-0266: ADR-0149 §3 offers a
  trial and never starts one on its own.
- **Keeping `b-2-05` and `b-4-03`, with the tenant's plan leaving them out.** Rejected: the
  shipped plan would then never open stage 1, and the blueprint would name as a process what
  no tenant can register — the fault ADR-0191 removed for B-9.01.
- **B-2.06 with a model proposing cancellations.** Rejected: without the real use a model's
  proposal has no ground, and UC-03 keeps cancelling with a person.
- **No bundle for B-2.06.** Rejected: the cost half of the row has a published source.

## 4. Which entry permits it

M2.6, with ADR-0191 §4 and NTC-0263 as precedent. The owner may overrule it in the pull
request.

## 5. The entry it proposes

None beyond NTC-0263's M2.13. Its counterpart: *a row of a blueprint's catalogue that the
instance serves for every tenant stands in no stage, and the README names where it is served.*
