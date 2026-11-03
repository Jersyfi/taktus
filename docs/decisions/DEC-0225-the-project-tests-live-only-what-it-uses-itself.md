# DEC-0225 — The project tests live only what it uses itself

**Category:** NON-BLOCKING
**Mode entry:** M4 (the owner's own accounts and what the project runs on), M2.5 (needs requests follow from it)
**Raised in:** the session of 2026-11-03, by the owner's message in conversation
**Issue:** none; the owner answered in conversation
**Needed by:** 2026-11-03
**Written after the answer:** the owner stated it in conversation on 2026-11-03; left out of the acceptance rate (DEC-0042).

## 1. What this is about

Sessions raised needs requests that asked the owner for accounts at services the project does
not use: a cloud bill (NEED-0035), and then, on the session's own proposal, the model costs at
OpenAI (NEED-0042). The connectors behind them were built for a customer, under DEC-0201.

## 2. Why you are being asked

Which services the project itself runs on is the owner's matter. No session can choose them.

**Sources checked:** DEC-0201 (connectors are product), CLAUDE.md §9 (a test that needs a credential runs on `main` only), ADR-0028 (needs requests), the open needs requests.

## 3. What you must decide

Whether the project provides accounts at services it does not use itself, so that their
connectors can be tested live.

## 4. What you need to know to decide

Each connector is proven against a fake of its service and the connector conformance suite.
Only a live run against the real service shows that the service behaves as its documentation says.

## 5. Options

### Option A — live tests only for what the project uses itself (recommended)

### Option B — an account at every service a connector serves

## 6. What is blocked

Nothing.

## 7. How to answer

In conversation.

## Outcome

**Decided:** 2026-11-03
**Answer:** Option A, in the owner's words: "Taktus selbst nutzt für seine Eigenentwicklung nur
Anthropic." A feature that comes from a customer is provided, "aber können diese selbst bei uns
niemals testen, weil es der Kunde dann selbst machen muss." (Taktus uses only Anthropic for its
own development. Features a customer needs are provided, but the project can never test them
itself, because the customer has to do it.)
**Reasoning given:** what customers use is not known and cannot all be tested.
**What it changes:**

1. **A needs request asks only for what the project itself runs on.** Today that is the model
   provider and coding agent (Anthropic), the repository service, the chat workspace, the
   password manager, the project's own cluster and its backup store. A session tests that list
   before it raises a need.
2. **A connector for a customer's system is product support.** It is proven against its fake and
   the conformance suite. A tenant that uses it creates the credential for its own instance
   (DEC-0201), and the first live run is the tenant's. What it finds reaches the project as a
   product finding (UC-6.12).
3. **Closed by this answer:** NEED-0035 (cloud bill), NEED-0036 (the Anthropic Admin key, which an
   account for an individual cannot have), NEED-0042 (OpenAI costs, raised by the session's own
   mistake and withdrawn), and NEED-0022 (the second coding agent's key, at a vendor the project
   does not use). The second coding worker stays proven against its stand-in.
4. **What the roadmap asks of the project's own instance** against outside systems is put to the
   owner in DEC-0226, because the roadmap is the owner's.
**Recorded in:** this pull request
