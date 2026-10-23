# NTC-0225 — UC-1.11: a person's own agent reaches Taktus, with the rights of their role

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-23
**Raised in:** [#603](https://github.com/Jersyfi/taktus/pull/603)
**How it follows:** the owner accepted W5 of DEC-0195 on 2026-10-13: Taktus as an MCP server, with rights per role, in `0.5.0`. Issue #406 states its verification conditions. No use case required it: UC-1.1 makes any channel's input a command, and names no surface an agent is offered tools on. UC-1.11 states W5 as a requirement, with the conditions of #406 and what follows from them.

## 1. What was decided

UC-1.11, *A person's own agent reaches Taktus, with the rights of their role*, component
`command`, state `specified`, version `0.5.0`. Its conditions are those of issue #406, and four
that follow from what the owner already accepted:

- every call is attributed to the identity and every act is recorded in the ledger (UC-1.7,
  UC-6.1);
- a client sees no more than the identity's roles may see (UC-6.4);
- the right to act is granted to a role, never to a named person (UC-7.3);
- no measure is computed from calls per person (principle 14).

The take-over tools of UC-4.19 are named, since its MCP point waits for this surface.

## 2. The evidence

- DEC-0195 §4, W5, and the research it rests on (`docs/research/2026-10-13-warp-review.md` §5).
- Issue #406, *How it is verified* and *Where the boundary lies*.
- UC-4.19 §2: "The web app, the chat and the MCP surface offer 'take over' on a running step."
- `docs/usecases/`: no use case names a surface an agent is offered tools on.

## 3. What was considered

- **Amending UC-1.1.** Rejected: UC-1.1 turns what a person writes into a command; here an agent
  calls tools, reads, and answers, and its rights are the subject.
- **No use case, the issue alone.** Rejected: the issue closes; the requirement must outlive it.

## 4. Which entry permits it

M2.7, *bringing a use case up to what the owner has already accepted*: here a feature the owner
accepted in DEC-0195. The owner may veto it within seven days of this pull request; a veto turns
it into a request under M3.15.
