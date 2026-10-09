# NTC-0087 — An anchored act halts at the step boundary

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-09
**Raised in:** [#79](https://github.com/Jersyfi/taktus/issues/79)

## 1. What was decided

Until now the product evaluated no anchor: a run at any level performed an act a tenant meant to
keep with a person. Now the run engine asks, before anything of a step starts, which of the
tenant's anchors name the step's act (ADR-0042):

- **A tenant's anchors are configuration.** `taktusctl anchors set` stores them; one that leaves
  the legal or the correction class empty is refused. A tenant that configured nothing holds the
  shipped default: one legal and one correction anchor, decided by the role `owner`.
- **An anchored step waits in `waiting_human`** with one decision request per anchor, at every
  level, before its level is applied. The rest of the run continues where it does not depend on
  the step. `taktusctl run --approve` does not confirm an anchored step.
- **A person holding the anchor's role answers** on the control plane's surface. The reading of
  the answer is sent back, and only a confirmed reading takes effect. The register gains an
  entry, and the step continues or is declined; a declined step halts the run with cause
  `declined`.
- **The recommended option of a request carries its reason**: `DecisionRequest.json` gains
  `options[].reason`, required on the recommended option.
- **Identities hold roles** (`taktusctl identity add --role`, `identity roles`).

What changes for the processes that exist: nothing they do today is anchored. The shipped default
anchors `legal.*`, `payment.release` and `correction.*`, and no bundle in the repository uses any
of them.

## 2. The evidence

- Issue #79's verification, from UC-7.4 §2 and UC-7.1 §2: an anchored process is halted with a
  decision request at each of levels 1 to 3; a free-text answer leaves the run waiting until the
  confirmation; an answered request has a register entry; the recommended option comes "with its
  reason".
- `tests/governance/test_anchors.py` holds each point, and `tests/adapters/rest/test_decisions.py`
  holds the surface.
- `grep -rn "legal\.\|payment\.release\|correction\." blueprints examples` finds no capability a
  bundle uses under the default's anchors.

## 3. What was considered

- **No anchors for a tenant that configured none.** Rejected: the set "can be reduced but never
  emptied" (ADR-0008), and an unconfigured tenant would have emptied it by default.
- **Anchors applied after the level.** Rejected: at level 2 the person would confirm a step first
  and decide its anchor second, for one act.
- **The reason of the recommendation inside its consequence.** Rejected: the shape would not show
  whether a reason was given, and a request without one would still be raised.

## 4. Which entry permits it

M2.4, *"A change of what the software does, made inside an agreed scope, that breaks no published
contract, moves no limit or autonomy level and says nothing public."* The scope is issue #79,
which the owner's backlog made ready. The contract change adds a field to a `v1` schema that no
released version uses (ADR-0019), so no published contract breaks. No limit and no level moves:
an anchor holds whatever the level, and lowers none.
