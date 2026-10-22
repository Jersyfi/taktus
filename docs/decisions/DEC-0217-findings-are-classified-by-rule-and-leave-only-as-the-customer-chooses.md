# DEC-0217 — Findings are classified by rule and leave only as the customer chooses; rc.28 and three tasks go ahead

**Category:** NON-BLOCKING
**Mode entry:** M3.15 (what a use case requires); DEC-0197 (handing a task to Taktus); the owner's act on a server (ADR-0028)
**Raised in:** the session that took up the milestones `0.1.0` to `0.3.0`, on 2026-10-21
**Issue:** none; the owner answered in conversation
**Needed by:** 2026-10-31
**Written after the answer:** the owner answered in conversation on 2026-10-22; left out of the acceptance rate (DEC-0042).

## 1. What this is about

- UC-6.12 §2 lets an instance raise a finding for "a capability no configured adapter offers". A lack the customer could fix by configuring an adapter the product ships, or a fault in the customer's own adapters, processes or bundles, then leaves the customer's instance as a product finding. The owner said such findings must never reach the project (DEC-0214).
- Findings must reach the project without a second app (DEC-0214).
- #317, #325 and #394 came back under P-03 version 21: two reworded the description's headings, one met a 502 from the egress proxy.
- The work of 2026-10-18 to 2026-10-21 is not yet on the instance, and #324's last point needs it there.

## 2. Why you are being asked

What a use case requires is the owner's (M3.15). Handing a task to Taktus is the owner's (DEC-0197). Installing a release on the instance is an act on its server.

**Sources checked:** UC-6.12, ADR-0112, DEC-0201, DEC-0214, DEC-0215.

## 3. What you must decide

Whether findings are classified as proposed, whether the three tasks go again, and whether rc.28 is tagged and installed.

## 4. What you need to know to decide

Each release can list the workers, connectors, capabilities and operations it ships. A rule can then tell a product's lack from a customer's.

## 5. Options

### Option A — classify by rule, let the customer choose the path, send to the project's instance; hand the three again; install rc.28 (recommended)

### Option B — keep UC-6.12 as it is

## 6. What is blocked

Sending findings from the business's instance; #317, #325, #394; #324's measurement.

## 7. How to answer

In conversation.

## Outcome

**Decided:** 2026-10-22
**Answer:** Option A. "Alles Freigegeben" (the owner's words: everything approved), to the session's three questions: the findings proposal, handing #317, #325 and #394 again with P-03 version 22, and tagging and installing rc.28.
**Reasoning given:** none beyond the proposals.
**What it changes:**

- **Findings, as the proposal stated it:**
  - A release carries the list of the adapters, capabilities and operations it ships.
  - A rule classifies every lack against that list: a *product candidate* where nothing shipped offers it; *local: configuration* where a shipped adapter offers it but is not configured; *local: own development* where the lack lies in an adapter, process or bundle the customer brought. A report by hand is a product candidate, its target chosen by the person who writes it.
  - What is local never leaves the instance. It reaches the customer's own owner-facing channel (UC-6.11), with what to configure where that applies.
  - The customer's operator chooses for product candidates: *off* (the default), *review* (each shown with the text that would leave; send, do not send, or "local for us", which is remembered), or *automatic* (rule-classified lacks only; a report by hand is always reviewed).
  - A finding leaves signed to the intake of the project's own instance, which opens or adds to the issue with the project's one app. A new sender is confirmed once by the owner, in the owner's channel, and each sender is rate-limited.
  - UC-6.12 §2 changes from "no configured adapter" to "no adapter the product ships", and gains the classification and the three levels. NEED-0031 (#533) is superseded by the pull request that builds this; nothing is needed from the owner.
  - The session placed the work in `0.4.0`, because it completes #446 and is wanted for the business's stage 0. The owner did not name a milestone.
- **#317, #325 and #394** are handed to Taktus again, after their failed attempts' branches are deleted (DEC-0205).
- **rc.28** is tagged from `main` and installed on the instance; the worker's conformance and S-01 run again after it, and #324's pod starts are measured before and after.

**Recorded in:** this pull request
