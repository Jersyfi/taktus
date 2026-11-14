# NTC-0291 — UC-1.14: a person builds in Taktus by conversation

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-11-14
**Raised in:** branch `area/conversation` of package F (concept mode, DEC-0222, DEC-0239)
**How it follows:** the owner decided in DEC-0239 item 6 that Taktus gets a conversation of its
own over its model port, in the web app and the chat, and that a vendor's agent program never
leads it. No use case required it: UC-1.8 requires a session in a project, each statement
sourced, and UC-1.11 a person's own agent. UC-1.14 states the owner's answer as a requirement.
Where the answer left a reading open, the stricter one in substance was taken (CLAUDE.md §8).

## 1. What was decided

UC-1.14, *A person builds in Taktus by conversation*, component `command`, version `1.0.0`, the
next free number of area 1. Three readings were settled, and ADR-0325 and ADR-0326 build them:

- **"As intuitive as a chat agent" does not mean "acts alone".** Every act Taktus proposes is
  read back and waits for the person's yes, as ADR-0008 requires of a free-text answer. The
  owner's words "Taktus führt" are read as: Taktus leads the conversation, not the decision.
- **"Over its model port" means as a run.** A model call outside a run would escape the budget
  and the ledger (control-plane.md §1). Every turn is a run of a process the operator names.
- **"In the chat" means after the rules.** The phrasebook's words and a tenant's triggers keep
  their meaning; the conversation takes only what is left.

## 2. The evidence

- DEC-0239, *What it changes*, item 6; `docs/vision/non-goals.md` (no agent runtime as a core
  product); UC-1.1 and NTC-0050 (the conversation is Taktus's).
- ADR-0008 (a reading confirmed before it counts); ADR-0261 (a message in a rollout channel is
  an input of a process, never a command).

## 3. What was considered

- **Acting on a clear request without a yes.** Rejected: an answer of a language model is a
  free-text reading of what the person meant; ADR-0008 asks for the reading to be confirmed.
- **The conversation as the session of UC-1.8 without a project.** Rejected: UC-1.8 requires
  every statement to name its source in the project's knowledge.

## 4. Which entry permits it

M2.7, *bringing a use case up to what the owner has already accepted*: here DEC-0239 item 6.
The owner may veto it within seven days of the pull request.
