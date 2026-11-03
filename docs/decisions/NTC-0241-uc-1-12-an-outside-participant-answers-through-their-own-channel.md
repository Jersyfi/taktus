# NTC-0241 — UC-1.12: an outside participant answers through their own channel

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-28
**Raised in:** branch `concept/package-a` (package A, concept mode, DEC-0222)
**How it follows:** the owner accepted the product outlook of 2026-10-12, which filed issue #337 for `0.5.0`: a supplier, client or authority answers a step through the channel they already use, without a Taktus account. The issue asks for the use case first (DEC-0190). No use case required it: UC-1.7 makes every command an identity's and gives an unknown sender only an offer to link, and UC-15.3 is about partner systems under a data contract, not a person's answer in a mail. UC-1.12 states #337 as a requirement, with its conditions made observable and two that follow from what the owner already accepted.

## 1. What was decided

UC-1.12, *An outside participant answers through their own channel*, component `command`,
version `0.5.0`, the next free number of its area (`docs/usecases/NUMBERING.md`). Its conditions
are those of #337, and two that follow:

- a free-text answer is said back and counts only once confirmed, because ADR-0008 forbids
  acting on free text silently;
- the question is an outward message under UC-7.6, because ADR-0142 holds every message that
  leaves the system to its frame.

Concept mode lets a new use case be written beside its implementation (DEC-0222). It was.

## 2. The evidence

- Issue #337, *How it is verified* and *Where the boundary lies*; DEC-0190.
- UC-1.7 §2, UC-15.3 §1, UC-7.6 §1.
- ADR-0008 §2, ADR-0040 §5, ADR-0142 §1.

## 3. What was considered

- **Amending UC-1.7.** Rejected: UC-1.7 requires that nothing executes without an identity. A
  participant's answer executes nothing of the organisation's, and folding it in would weaken
  the rule it states.
- **Amending UC-15.3.** Rejected: a partner interface is a system under a data contract; a
  participant is a person in a conversation.
- **No use case, the issue alone.** Rejected: the issue closes; the requirement must outlive it.

## 4. Which entry permits it

M2.7, *bringing a use case up to what the owner has already accepted*: here the issue the
owner accepted with the product outlook. The owner may veto it within seven days of the pull
request that lands the concept; a veto turns it into a request under M3.15.
