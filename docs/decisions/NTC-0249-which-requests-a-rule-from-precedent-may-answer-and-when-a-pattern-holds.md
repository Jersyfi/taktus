# NTC-0249 — Which requests a rule from precedent may answer, and when a pattern holds

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-30
**Raised in:** the branch `concept/package-b--level4` (package B, DEC-0222), for issue #648
**How it follows:** ADR-0008 makes the register a precedent memory from which Taktus proposes rules "without control being given away", and lets the tenant reduce its strategic class while the legal and correction classes are never emptied; ADR-0088 says no tenant configuration removes a step's own `ask`; ADR-0152 makes an approval and a sample a check on a value. A rule a person adopts is therefore read as a reduction of the tenant's own strategic anchor for one kind of request, the only reduction the sources already allow. Where a looser and a stricter set were both consistent, the stricter one in substance was taken, and the number of precedents was set where one week of daily runs reaches it.

## 1. What was decided

- **A rule may answer only a request raised by a strategic anchor of the tenant's own
  configuration.** No rule is ever proposed for a request of the class `legal` or `correction`,
  for the frame's own anchors (class `legal`), for a step's own `ask`, for an approval or a sample
  (class `domain`), or for a proposal to change a process (class `conceptual`, or no anchor).
  These are what UC-7.10 calls an act an anchor keeps with a person.
- **A kind of request** is one anchor at one step of one process.
- **A pattern is consistent** when the five most recent decisions of the kind, all decided after
  the last proposal of the kind was decided, chose the same option, without modifications, by
  the same role, and none was taken by a rule.
- **The proposal is addressed to the role that decided the precedents**, class `strategic`.

## 2. The evidence

Issue #648 asks that a rule over an act an anchor keeps with a person is never proposed. Read
literally, every anchor keeps its act with a person, and no rule could ever exist; ADR-0008
still promises them. CLAUDE.md §8 and ADR-0008 both say the anchor set can be reduced but never
emptied, and ADR-0008 names which classes cannot be emptied.

## 3. What was considered

- **Every anchor and every ask may be answered by a rule.** Rejected: it would let a count
  decide a legal act, and remove an ask the process declared, against ADR-0008 and ADR-0088.
- **No anchored request at all.** Rejected: then the feature answers nothing. The strategic class
  is the one the tenant may reduce, and the rule is that reduction, made by a person.
- **Three precedents.** Rejected as too few: three agreeing answers happen by chance in a week.
- **Ten precedents.** Not taken: for a weekly process that is more than two months.
- **Address the proposal to the owner.** Not taken: the role that decided the act knows it best,
  and still decides it by accepting the rule.

## 4. Which entry permits it

No entry of modes 3 or 4 names which requests a rule may answer or how many precedents make a
pattern. The anchors stay as configured: the tenant's set is not changed, and a rule exists only
once a person of the anchor's role accepted it. So M2.6 applies.

## 5. The entry it proposes

**M2.10** — *The bound of a mechanism that proposes, which a person then accepts or declines:
how many precedents make a pattern, and which classes of request it may never touch, chosen
strictly from what the ADRs already keep with a person.*
