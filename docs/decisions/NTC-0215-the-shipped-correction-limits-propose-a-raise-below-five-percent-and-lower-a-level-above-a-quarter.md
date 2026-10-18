# NTC-0215 — The shipped correction limits propose a raise below five percent, and lower a level above a quarter

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-18
**Raised in:** issue [#429](https://github.com/Jersyfi/taktus/issues/429), in the pull request that closes it
**How it follows:** UC-7.5 and UC-03 §3 make the numbers for a raise and for a fall the tenant's to set ("The tenant sets the numbers"), and name no value a tenant holds before it sets one. UC-7.5 §1 says that lowering autonomy makes the system safer and is never held for an approval; UC-7.1 says a raise needs evidence and a person. Where two defaults were both consistent with these, the stricter in substance was taken: a raise is proposed only on a month of clean evidence, and a level falls before a week of frequent corrections is over.

## 1. What was decided

A tenant that set no correction limits holds the shipped default (ADR-0110 §5):

1. **A raise is proposed** when at least 20 decisions were made within 28 days, the first of them
   at least 4 weeks ago, and the correction rate is below 5 % over 7 days and over 28.
2. **A level falls one level** when, over 7 days, at least 4 decisions were made and the
   correction rate is above 25 %.

`taktusctl corrections configure` sets every value; the default is product, not the project's.

## 2. The evidence

- A process at level 2 that runs daily, with a proposal per run, reaches 20 decisions within a
  month. Five percent of 20 is one correction: a raise is proposed only when at most one of them
  was changed.
- A process that is corrected in one of every four proposals is wrong too often to run with less
  oversight. Four decisions keep a single early correction from lowering it.
- `tests/components/governance/test_corrections.py`
  `test_the_shipped_limits_hold_until_a_tenant_sets_its_own`.

## 3. What was considered

- **No default; nothing is counted until a tenant sets its limits.** The second tenant's first
  proposals would go uncounted, and UC-7.5 §4 asks that they count from the first. Rejected.
- **A raise at 10 %.** One correction in ten is still a person changing what Taktus would have
  done. Rejected for 5 %.
- **A fall at 50 %.** A process corrected every other time would keep its level for a week of
  such corrections. Rejected for 25 %.
- **No minimum of decisions for a fall.** A single correction on the first proposal would lower
  a process. Rejected: a fall raises an incident, and a false one teaches people to ignore them.

## 4. Which entry permits it

No entry of modes 3 or 4 names the default of a tenant's correction limits. M3.9 names raising a
level, and a raise still needs a person's approval; the limits only decide when Taktus proposes
one. M3.10 names limits on spending — a budget, a quota, a compute bound, a margin — and a
correction rate limits no spending. No entry of mode 2 names it either, so M2.6 applies.

## 5. The entry it proposes

The entry NTC-0212 proposed, **M1.24** — *the shipped default of a tenant setting that limits no
spending* — covers it: a threshold for a report or a level's fall, a window it is counted over,
where the use case makes it the tenant's to set.
