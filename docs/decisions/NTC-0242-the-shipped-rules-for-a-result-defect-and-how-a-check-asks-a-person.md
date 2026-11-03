# NTC-0242 — The shipped rules for a result defect, and how a check asks a person

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-28
**Raised in:** the branch `concept/package-a` (package A, DEC-0222), for issues #223 and #92
**How it follows:** ADR-0023 §3 and principle 10 require that some rule always brings a person in, and the shipped set holds four that do; ADR-0022 §3 keeps every correction of what left with a person at every level, which the fourth rule brings forward; principle 8 asks for the same choice of samples every time, which a digest gives and a draw does not. Where a narrower and a wider shipped set were both consistent with these, the wider one in substance was taken, with no ceremony added: the tenant reduces it with one configuration. This follows the precedent of NTC-0212, NTC-0226 and NTC-0228 for the shipped watch.

## 1. What was decided

- **The rules a tenant that configured nothing holds** for a result defect (ADR-0023 §2,
  ADR-0153): stop when an `exact` result has left the system and a legal anchor lies downstream;
  escalate when the strictest class affected is `exact` or `sourced`; escalate when the window
  is longer than seven days; escalate when anything affected has left the system. They are part
  of the tenant's watch configuration, and a set with no rule that escalates or stops is refused.
- **An approval's request and a sample's request are of class `domain`**, addressed to the
  check's role. An approval blocks the step; a sample blocks nothing (ADR-0152).
- **A sample is chosen by a digest of the run and the step**, so that the same results are chosen
  for the same runs.

## 2. The evidence

ADR-0023 §2 names the criteria and gives two example rules for the shipped set, without numbers
for the window. ADR-0152 needed a class for the two requests, and the decision request contract
offers five. The issue #223 requires "the same results for the same runs".

## 3. What was considered

- **No rule on the window, as ADR-0023's second example reads without a number.** Rejected: a
  criterion without a threshold fires on nothing or on everything. Seven days is one week of
  daily runs; the tenant may change it.
- **An escalation for anything that left, beyond the two examples.** Kept: a correction of what
  left is a person's at every level (ADR-0022 §3), so a person is brought in early.
- **Class `correction` for an approval.** Rejected: nothing has left the system when a value is
  approved; `correction` is ADR-0022's class for what has. `domain` is the class of a question
  about the business's facts.
- **A random draw for sampling.** Rejected: it would choose differently each time it is asked.

## 4. Which entry permits it

No entry of modes 3 or 4 names the shipped thresholds of the rule of ADR-0023, nor the class of
the request a check raises. M3.10 names limits on spending; these spend nothing. No entry of mode
2 names them either, so M2.6 applies.

## 5. The entry it proposes

The entry NTC-0212 proposed covers the thresholds: **M1.24** — *The shipped default of a tenant
setting that limits no spending*. For the class of a request a mechanism raises it proposes
**M1.25**: *the class of a decision request a mechanism raises, chosen from the contract's
classes by what the question is about*.
