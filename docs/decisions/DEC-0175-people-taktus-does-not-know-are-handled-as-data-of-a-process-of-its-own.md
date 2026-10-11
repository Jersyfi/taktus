# DEC-0175 — People Taktus does not know are handled as data of a process of its own

**Category:** NON-BLOCKING
**Mode entry:** M3.15
**Raised in:** issue [#245](https://github.com/Jersyfi/taktus/issues/245), from the owner's direction recorded with DEC-0127; recorded in the pull request that records the owner's answers of 2026-10-11 (evening)
**Issue:** [#245](https://github.com/Jersyfi/taktus/issues/245)
**Needed by:** before #245 is built
**Written after the answer:** the session put the proposal in conversation on 2026-10-11 and the owner accepted it there; the record was written from it; left out of the acceptance rate (DEC-0042).

## 1. What this is about

The repository is public. People Taktus does not know open issues and pull requests in it. Today
an event from an unknown sender is answered with an offer to register and nothing else is done
(UC-1.7). The owner wants such contributions handled by a process of Taktus's own, without the
person registering (DEC-0127).

## 2. Why you are being asked

What a requirement requires is the owner's (M3.15). No use case says what happens to an event
from an unknown sender beyond the offer.

**Sources checked:** UC-1.7 (an unknown sender's event becomes no command of theirs), UC-4.14
and ADR-0048 (an event acts for its sender as placed), ADR-0012 and DEC-0044 (no outside
contribution before the licence), principle 4 (omnichannel), principle 11 (processing a person's
data needs a stated basis and a notice), principle 14, and DEC-0127. None says what such a
process must do.

## 3. What you must decide

Whether, and how, an event from a person Taktus does not know starts a process.

## 4. What you need to know to decide

- The person would never act: what the process does, it does for its owner.
- The person's public data on the repository service would be processed; that needs a notice in
  the repository's contributing guide, whose wording is the owner's (M3.7).
- Blocking a person is an act on that person.

## 5. Options

### Option A — a triage process acting for its owner, the sender as data (recommended)

- **Meaning:** a new use case. An event from an unknown sender on a public channel starts a
  triage process that acts for the process's owner; the sender is its data, never its actor and
  never given a right. The process classifies the contribution — a defect, a feature with the
  version it would belong to, spam — and prepares it for the owner. What the owner approves stays
  open and enters the backlog; what is declined is closed with the reason. Spam is closed
  automatically. **Blocking a sender stays with a person** (an anchor). An outside pull request is
  triaged and held, never merged, while the licence is open (DEC-0044). The session drafts the
  contributing guide's notice; its wording is the owner's (M3.7).
- **Consequence:** UC-1.7 gains a pointer to the new use case; #245 is built on it.
- **Why recommended:** it follows the owner's direction while keeping UC-1.7: the sender never acts, and the act on a person stays with a person.

### Option B — unknown senders keep receiving only the offer to register

### Option C — the owner's own wording

## 6. What is blocked

#245.

## 7. How to answer

"DEC-0175: Option A.", "DEC-0175: Option B." or the owner's own wording.

## Outcome

**Decided:** 2026-10-11
**Answer:** Option A. "Proposal accepted." (the owner's words, translated).
**Reasoning given:** the recommendation; the owner's direction of DEC-0127 that the project stays open to its community.
**Recorded in:** this pull request; the use case is written with #245
