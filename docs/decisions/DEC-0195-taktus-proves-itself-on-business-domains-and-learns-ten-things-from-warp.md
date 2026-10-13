# DEC-0195 — Taktus proves itself on business domains, and learns ten things from Warp

**Category:** NON-BLOCKING
**Raised in:** a session of 2026-10-13 that compared Taktus with Warp at the owner's request; recorded in the pull request of its own that records the answer
**Issue:** none; the owner answered in conversation, and this record is the question with the answer
**Needed by:** 2026-10-13
**Written after the answer:** the owner answered in conversation on 2026-10-13; the record was written from it; left out of the acceptance rate (DEC-0042).

## 1. What this is about

The owner found Warp close to Taktus and asked whether Taktus must change at its foundations.
Warp builds "software factories": agents turn tickets into reviewed pull requests. Every
milestone of Taktus up to `1.0.0` proved Taktus on software or IT operations, the field where
Warp is far ahead. What sets Taktus apart was not proven on a real operation before `1.0.0`. The
evidence is `docs/research/2026-10-13-warp-review.md`.

## 2. Why you are being asked

Changing a milestone's completion criterion is a change of direction (M3.2), and so is accepting a
feature. Who the second tenant is can only be answered by the owner (M4).

**Sources checked:** `docs/vision/` (non-goals, market, beyond-1.0, history), `docs/roadmap.md`,
ADR-0013, ADR-0030, ADR-0092, both anchor pages and the register. The non-goal "no coding agent
and no agent runtime as a core product" bounds the answer. No source places the proof of Taktus.

## 3. What you must decide

- **E1:** where Taktus proves itself (W1).
- **E2:** whether the worker contract gains three extensions before it freezes (W2).
- **E3:** whether W3 to W10 are adopted.
- **E4:** who the second tenant is.

## 4. What you need to know to decide

| | Proposal | Issue | Milestone |
|---|---|---|---|
| W1 | the second tenant is a real operation | #400 | `0.4.0` |
| W1 | a process of the second tenant at level 3 with an enforced anchor | #401 | `0.6.0` |
| W1 | the second domain is incoming invoice to payment release; IT operations (#95) move after `1.0.0` | #402 | `0.7.0` |
| W2 | outbound-only binding, steering and handover in the worker contract | #403 | `0.6.0` |
| W3 | a running step taken over under a lease | #404 | `0.5.0` |
| W4 | a first process in ten minutes, measured | #405 | `0.5.0` |
| W5 | Taktus as an MCP server, with rights per role | #406 | `0.5.0` |
| W6 | `SKILL.md`, `AGENTS.md`, a bundle validator without an instance | #407 | `0.4.0` |
| W7 | evaluation cases per process, versions compared on them | #408 | `0.5.0` |
| W8 | the trace inside a step, live, shareable by role | #409 | `0.5.0` |
| W9 | vendors' MCP servers as connector candidates | #410 | `0.6.0` |
| W10 | a software factory as a worker | #411 | `0.6.0` |

**Examined and kept, with reasons in the research:**

- Taktus does not become a software factory.
- It does not build on Warp's platform.
- No language model steers the flow.
- The ledger stays content-free.

## 5. Options

### Option A — as proposed, with a plan B for the second tenant (recommended)

- **Meaning:** E1, E2 and E3 as in §4.
- **Plan B for E4:** if the complete use case of a real business does not arrive by 2026-10-31, the second tenant is the owner's own household administration from 2026-11-01.
  - It is a family tenant, which the vision names as a customer.
  - Its documents are real and in the owner's hands.
  - Its process has the same shape as the second domain: a document is read and classified, its amount is checked as `exact`, and a person releases each payment.
- **What plan B proves less than a business:**
  - no department is crossed;
  - there are few cases a day, so maturation needs longer to collect 500 of them.
- **If the business case arrives later,** it becomes the third tenant and carries the second domain.

### Option B — keep the proof on software and IT operations

- **Meaning:** the roadmap stays; only W3 to W10 are adopted.

## 6. What is blocked

Nothing until 2026-10-31. Then #400 starts on plan B unless the business case is there.

## 7. How to answer

"Warp-Ausblick: E1: Option A. E2: Option A. E3: alle W3 bis W10 übernehmen." and, for E4, who the second tenant is.

## Outcome

**Decided:** 2026-10-13

**Answer:** Option A. "E1: Option A. E2: Option A. E3: alle W3 bis W10 übernehmen. E4: I am waiting to be sent the complete use case of a business, which I expect by the end of the month. There is a risk I will not receive it, so think of a plan B." (the owner's words; E4 translated)
**Reasoning given:** "This is a decisive choice that shapes the future of Taktus." (from the request, translated)

**Plan B, as the session sets it:** the owner's household administration from 2026-11-01, as in §5. The need is NEED-0027.

**What it does not change:**
- the vision and the non-goals: Taktus still uses coding agents as workers;
- the project's own development with P-01 to P-03;
- the licence (DEC-0044);
- DEC-0029, which must now be answered before `0.7.0`.

**Recorded in:** this pull request:
- `docs/roadmap.md`;
- `docs/usecases/AF-02-it-operations.md` and its index row;
- `docs/research/2026-10-13-warp-review.md`;
- `docs/status.md`;
- NEED-0027;
- the issues #400 to #411;
- #95 moved to `2.0.0`.
