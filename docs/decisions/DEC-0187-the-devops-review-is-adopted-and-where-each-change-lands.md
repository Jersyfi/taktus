# DEC-0187 — The DevOps review is adopted, and where each change lands

**Category:** NON-BLOCKING
**Raised in:** a session of 2026-10-12 that reviewed the concept as a DevOps expert at the owner's request; recorded in the pull request of its own that records the answer
**Issue:** none; the owner answered in conversation, and this record is the question with the answer
**Needed by:** 2026-10-12
**Written after the answer:** the owner answered in conversation on 2026-10-12; the record was written from it; left out of the acceptance rate (DEC-0042).

## 1. What this is about

The owner asked for a critical review of whether Taktus's concept holds up in production. The
review was to look at the whole range of customers, from a person to an operator that hosts
Taktus for others, and at whether a cluster's resources are used sensibly. The session proved
every finding by an experiment against the real code
(`docs/research/2026-10-12-devops-review.md`). Twenty findings remained:

- a deadlock in the ledger;
- listing runs that blocks the process;
- a cache that never empties;
- cache writes booked too cheaply;
- the project leaking into the product;
- the tenant list stored in an environment variable;
- colliding lock keys between tenants;
- no fairness between tenants or departments;
- one write queue per tenant;
- whole-ledger reads;
- waits that hold a runner's place;
- a pod start for every estimate;
- whole-run rewrites on every commit;
- no small install profile;
- a single node;
- a restore that loses the artifacts;
- upgrades that drop readiness;
- no path that tells a person something needs action;
- four stale documents;
- the project's own ceremony.

The owner then asked the session to place each finding in a milestone, all the way up to a
`2.0.0` for operators. The session was also to settle the review's six open questions with the
answer that fits Taktus best.

## 2. Why you are being asked

Accepting a feature or a change of direction is M3.2. Where each item lands is the session's
(M1.7, M1.8). Settling the open questions on the owner's behalf needs the owner's leave, because
some of them shape the product for operators. The owner gave that leave.

**Sources checked:** ADR-0013 (A: several instances, load spread), ADR-0020 (tenants and
instances), ADR-0006 (the ledger as the one source), ADR-0087 (backup), `docs/roadmap.md`, both
anchor pages and the register. Each source states a promise this review found unkept or a scope it
found unbounded. None places the changes.

## 3. What you must decide

Whether the findings are adopted, and whether the session places them and answers the open
questions.

## 4. What you need to know to decide

Each change is an issue in the milestone named below, with its verification condition. An ADR
comes first wherever the change touches an architectural decision.

| Finding | Issue | Milestone | Why there |
|---|---|---|---|
| D1 ledger deadlock | #309 | `0.3.0` | a fault today, on the installed instance |
| E4 listing runs | #310 | `0.3.0` | the web app of `0.3.0` reads it |
| M1 unbounded cache | #311 | `0.3.0` | a crash today on small machines |
| G1 cache writes, `Retry-After` | #312 | `0.3.0` | money recorded too low |
| X1 the project inside the product | #313, ADR-0092 | `0.3.0` | before the second tenant inherits it |
| K4 stale documents | — | here | DEC-0191 |
| T2 lock keys | #317 | `0.4.0` | before the second tenant |
| T1 tenants created by a command | #318 | `0.4.0` | the second tenant is created with it |
| T3 fair claims between tenants | #319 | `0.4.0` | two tenants share runners from then on |
| E1 waits park the run | #320 | `0.4.0` | the pipeline wait was 64 % of a run |
| L2 no whole-ledger read on a hot path | #321 | `0.4.0` | method maturation reads the calibration |
| K2 restore with the artifacts | #322 | `0.4.0` | the instance is production (DEC-0057) |
| K5 action needed reaches a channel | #323 | `0.4.0` | with K2 |
| E2 no unit per estimate, one egress gateway | #324 | `0.4.0` | the second coding worker runs on the cluster |
| E3 writes only what changed | #325 | `0.4.0` | cheap |
| K6 the small install profile | #326 | `0.4.0` | for the families and small businesses of the vision |
| K3 upgrades without a readiness gap | #330, ADR-0093 | `0.5.0` | the rule holds from now on, the range check is built then |
| L1 one chain per run | #341 | `0.7.0` | before the contracts freeze of `1.0.0`: the hash rule is public |
| K1 object store port, a highly available profile | #342 | `0.7.0` | production in a second domain |
| T3 fairness and quotas per department | #343 | `0.7.0` | corporations at production use |
| K2 point-in-time recovery, targets per profile | #346 | `1.0.0` | the restore drill of the road |
| K5 scanned and signed images, a `main` image | #347 | `1.0.0` | the external security review |
| T1 thousands of idle tenants at no cost | #350 | `2.0.0` | operators |
| an operator's tenant lifecycle | #351 | `2.0.0` | operators |
| an operator's metrics, fleet upgrades | #353 | `2.0.0` | operators |
| P7 six working rules | #314, #315, #316 | `0.3.0` | DEC-0189 |

**The open questions, and the answers that fit Taktus best:**

1. **Who creates a tenant, and who chooses its identifier?** An administrator of the instance
   creates it, through a command or the HTTP surface. Taktus generates the identifier, and a
   display name is separate. A customer never chooses an identifier. This closes the attack T2
   shows and needs no list in an environment variable (#318, #317).
2. **How fast does the ledger grow at a real customer?** It is not guessed. The target is that no
   read on a hot path depends on a tenant's history (#321). The growth per profile is measured by
   S-04 on the road to `1.0.0`, beside the load measurement.
3. **Do providers report cache writes at the top level?** The task that fixes the adapter verifies
   this against the endpoints in use, within the spend cap of M2.8, and records it as a notice
   (#312).
4. **What does a real pod start cost?** The task that removes the probe unit measures it on the
   installed instance before and after, under DEC-0179 (#324).
5. **How large is a corporation's tenant?** No absolute figure is promised before S-04 measures
   one. The target is relative: with eight writers in one tenant, the commits per second are at
   least four times one writer's (#341). Today the ratio is 1.4.
6. **How do the project's licensing and billing fit?** As bundles of the project's own tenant,
   on the generic accounting, never in product code. This is DEC-0188 and ADR-0092; the work is
   #354 in `2.0.0`, after the licence (DEC-0044).

## 5. Options

### Option A — adopt everything, placed and answered by the session (recommended)

- **Meaning:** the twenty findings become the issues above, and the six answers stand.
- **Consequence:** the milestones `0.3.0` to `0.7.0` grow, and `2.0.0` exists for operators.
- **Effort:** the issues' own.
- **Reversibility:** each placement is M1.7 and can move; each answer can be revisited by the owner.
- **Why recommended:** the owner's answer, below.

### Option B — adopt only the faults

- **Meaning:** D1, E4, M1 and G1 only.

## 6. What is blocked

Nothing.

## 7. How to answer

"DEC-0187: Option A." or "DEC-0187: Option B."

## Outcome

**Decided:** 2026-10-12
**Answer:** Option A. "From the Taktus optimisation proposal I want to adopt everything. Think about what should be worked in, from now up to which later milestones, or even only in a version 2.0 of Taktus — for points about several tenants, or corporations and operators, so that this is already recorded for the future version. But the final decision is yours, since you can best see what makes sense as a division. For the open questions, just set what fits Taktus best and I will accept it for now." (the owner's words, translated)
**Reasoning given:** customers will range from a person or a family to large corporations and operators that provide Taktus to others. The customers decide how far and how large Taktus is used.
**What it does not change:** what a use case requires. Where a change needs a requirement, the use case is written first, as its issue says. The licence stays DEC-0044.
**Recorded in:** this pull request:
- the issues #309 to #354 and the milestone `2.0.0`;
- `docs/roadmap.md`;
- `docs/research/2026-10-12-devops-review.md`;
- ADR-0092, ADR-0093;
- `docs/status.md`.
