# NTC-0247 — UC-1.13: a person sees what they may ask Taktus for

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-30
**Raised in:** branch `concept/package-b--views` (package B, concept mode, DEC-0222)
**How it follows:** the owner accepted the product outlook of 2026-10-12 (DEC-0190), which filed issue #340 as F9 for `0.6.0`: a list of the processes a person may start, each started as an ordinary command through any channel, never a ticket portal. The issue asks for the use case first. No use case required it: UC-1.1 makes every channel's request a command but lists nothing, and UC-1.11 lists processes only to a person's own agent. UC-1.13 states #340 as a requirement, with its conditions made observable and one that follows from what the owner already accepted.

## 1. What was decided

UC-1.13, *A person sees what they may ask Taktus for*, component `command`, version `0.6.0`, the
next free number of its area (`docs/usecases/NUMBERING.md`). Its conditions are those of #340:
every entry starts the same command a chat or command-line request would, and nothing is a
ticket, a queue or a service-level agreement. One follows:

- a start asked in the chat is read back and counts only once confirmed, because ADR-0008
  forbids acting on free text silently.

Concept mode lets a new use case be written beside its implementation (DEC-0222). It was.

## 2. The evidence

- Issue #340, *How it is verified* and *Where the boundary lies*; DEC-0190, F9.
- `docs/research/2026-10-12-market-review.md` §2.2.4, which names the risk of a ticket portal.
- UC-1.1 §1, UC-1.11 §2, ADR-0008 §2, ADR-0131 §3.

## 3. What was considered

- **Amending UC-1.11.** Rejected: UC-1.11 is the surface of a person's own agent; the list is for
  the person, through every channel.
- **No use case, the issue alone.** Rejected: the issue closes; the requirement must outlive it.

## 4. Which entry permits it

M2.7, *bringing a use case up to what the owner has already accepted*: here the issue the owner
accepted with the product outlook. The owner may veto it within seven days of the pull request.
