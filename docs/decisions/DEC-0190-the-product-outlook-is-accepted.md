# DEC-0190 — The product outlook is accepted

**Category:** NON-BLOCKING
**Raised in:** a session of 2026-10-12 that looked at the market as a product owner at the owner's request; recorded in the pull request of its own that records the answer
**Issue:** none; the owner answered in conversation, and this record is the question with the answer
**Needed by:** 2026-10-12
**Written after the answer:** the owner answered in conversation on 2026-10-12; the record was written from it; left out of the acceptance rate (DEC-0042).

## 1. What this is about

The owner named four products to look at: Zenkit, the ServiceNow AI Platform, LiteLLM and
OmniRoute. The session was to take over only what fits Taktus, translate it for Taktus, and show
it so that it can be decided. The session checked every idea against the fourteen principles,
dropped what does not fit, and showed the rest as clickable mock-ups. The evidence and the
screens are in `docs/research/2026-10-12-market-review.md`.

## 2. Why you are being asked

Accepting a feature is M3.2. A requirement new beyond the owner's definition is M3.15.

**Sources checked:** `docs/vision/` (principles 1, 7, 11, 13, 14; the non-goals), UC-4.2,
UC-4.11, UC-6.7, UC-8.2, UC-8.6, UC-9.3, UC-14.3 and UC-15.4, ADR-0003, ADR-0009, ADR-0012,
`docs/vision/beyond-1.0.md`, both anchor pages and the register. They bound each idea. None of
them accepts one.

## 3. What you must decide

Whether the proposals are accepted as proposed.

## 4. What you need to know to decide

| Proposal | From | Issue | Milestone |
|---|---|---|---|
| F7 a model price list imported into the versioned price table | LiteLLM | #327 | `0.4.0` |
| F7 an ordered chain per model purpose, switched at the step boundary; a gateway only as a pass-through | LiteLLM | #328 | `0.4.0` |
| F9 rehearse a version straight from the plan dialogue | Zenkit | #329 | `0.4.0` |
| F2 a human step and a fallback to a person name a role | Zenkit | #331 | `0.5.0` |
| F4 one register of everything that acts for a tenant, with an emergency stop and an AI Act inventory | ServiceNow | #332 | `0.5.0` |
| F5 what breaks if an adapter goes, where a wrong result went, where data goes | ServiceNow | #333 | `0.5.0` |
| F6 how a process really runs: variants, waiting, proposals | ServiceNow | #334 | `0.5.0` |
| F9 a stage view for participants; input checks as visible steps; outside participants through their own channel | both | #335, #336, #337 | `0.5.0` |
| F1 the organisation seen as value streams, with role swimlanes and department crossings | Zenkit | #338 | `0.6.0` |
| F8 connectors in images of their own | own | #339 | `0.6.0` |
| F9 what a person may ask Taktus for | ServiceNow | #340 | `0.6.0` |
| F3 a role's profile derived from the processes, exportable as a draft position description | Zenkit | #344 | `0.7.0` |
| F9 BPMN in as a plan draft and out as an export | Zenkit | #345 | `0.7.0` |
| F8 a catalogue with signatures and three tiers: *reference*, *verified* in the instance's own configuration, *community* up to level 2 | own | #348 | `1.0.0` |
| F9 a foreign agent as a worker through an A2A binding | ServiceNow | #349 | `1.0.0` |
| F7 each hosted tenant's own model credentials, budgets per unit, the operator's margin | LiteLLM | #352 | `2.0.0` |

**Dropped, each for a principle:**
- OmniRoute as infrastructure (principle 11; providers' terms; its security record);
- a gateway's budget as a second authority (ADR-0005);
- routing or caching hidden in a gateway (UC-8.2);
- LiteLLM as a library inside Taktus's process (its supply-chain incident of March 2026);
- a data platform of Taktus's own (principle 1);
- a language model choosing agents at run time (UC-4.2);
- analytics about employees or cost per user (principle 14);
- Kanban, Gantt, wiki, chat and form builders (principle 1);
- drawing processes as the way to build them (a non-goal);
- pricing per user (ADR-0010).

**The licence.** The catalogue's community tier waits for DEC-0044, which stays open with the
timing the owner set on 2026-10-08. The session's proposal that the contracts and the conformance
suite carry a permissive licence is common to every option DEC-0044 offers. It answers nothing
about the control plane's licence.

**Use cases.** Each feature's issue says its use case is written first. A use case that follows
from a feature accepted here is a notice under M2.7 (DEC-0189, rule 5).

## 5. Options

### Option A — accept as proposed (recommended)

- **Meaning:** every proposal above becomes its issue in its milestone, and the dropped list
  stands.
- **Consequence:** `0.4.0` to `2.0.0` grow by the features above.
- **Reversibility:** each feature can be withdrawn before it is built.
- **Why recommended:** the owner's answer, below.

### Option B — accept a selection

## 6. What is blocked

Nothing.

## 7. How to answer

"DEC-0190: Option A." or "DEC-0190: Option B." with the selection.

## Outcome

**Decided:** 2026-10-12
**Answer:** Option A. "For the Taktus product outlook I accept everything you proposed, and it shall be implemented as you proposed." (the owner's words, translated)
**Reasoning given:** none beyond the answer.
**What it does not change:** the licence (DEC-0044, M4.1); the price and the accounting basis (M4.2, M4.3); principle 14, which every view above must keep in its data model.
**Recorded in:** this pull request:
- the issues #327 to #354 named above;
- `docs/roadmap.md`;
- `docs/research/2026-10-12-market-review.md`.
