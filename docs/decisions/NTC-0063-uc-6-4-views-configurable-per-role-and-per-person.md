# NTC-0063 — UC-6.4: views configurable per role and per person

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-09
**Raised in:** [#136](https://github.com/Jersyfi/taktus/pull/136)
**How it follows:** the owner's project definition, version 2, UC-6.4, acceptance criteria: views are "configurable per role AND per person"; a person can hold several views at the same time; visibility follows the organisation's structure (UC-1.4). The amendment writes the per-person half as a condition and bounds it by principle 7, which the use case already applies: nobody sees what they are not entitled to.

## 1. What was decided

`docs/usecases/reporting/UC-6.4-role-based-views.md` gains a requirement. Section 1 says that which
role sees what is configured per role and per person, that a person can hold several views at once,
and that who sees what follows the organisation's structure. Section 2 gains the condition: a view
can also be given to one person beyond their roles, by configuration, and giving a view never widens
what that person is entitled to see. Section 4 names the restoration.

## 2. The evidence

- Definition version 2, UC-6.4, acceptance criteria, as quoted above. The use case, written against
  the earlier version and accepted with DEC-0030, configured views per role only.
- Principle 7 and the existing conditions of UC-6.4: a figure reaches only the roles entitled to it.
  The per-person half is therefore bounded by entitlement, as the definition's own principle requires.
- Principle 14 is untouched: a view given to a person says what that person sees, never what is said
  about them.

## 3. What was considered

- **Per person without the bound.** Rejected: a view given to a person would then be a way around the
  declared entitlement of each figure, which UC-6.4 and principle 7 forbid.
- **Asking it in DEC-0087.** Rejected: the condition restores the definition; the bound is the
  vision's, not an addition. DEC-0041 makes restoring the session's.

## 4. Which entry permits it

M2.7, *"Bringing a use case up to the owner's own definition: an amendment of what a use case
requires that only restores what `docs/vision/` and the owner's project definition already
require."* The amendment restores definition UC-6.4 within principle 7 and adds nothing beyond them.
