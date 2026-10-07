# NTC-0014 — UC-1.1 carries the sender's identity, context and reply address

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-01
**Raised in:** [#52](https://github.com/Jersyfi/taktus/pull/52)
**How it follows:** the owner's project definition, version 2, UC-1.1 and UC-1.7: every normalised command carries the sender's identity, its context and its reply address. The amendment writes that sentence into section 2 as a condition, and narrows section 3 from "not identity" to "not authorisation", because the definition puts carrying the identity inside the use case and leaves only whether the sender may act outside it.

## 1. What was decided

`docs/usecases/command/UC-1.1-commands-from-any-channel.md` was amended in two places.

- **Section 2** gains a condition: every command carries the identity of its sender, its
  context and the address a reply goes to.
- **Section 3**: "Not identity. Who the sender is, and whether they may give this command, is
  the identity component's" became "Not authorisation. Whether the sender may give the command
  is the identity component's; that the command carries who sent it is this use case's."

"Proven so far" says that the new condition is not checked on its own yet. The order in which
channels are connected stays the roadmap's (M1.7), as section 3 already said.

## 2. The evidence

- DEC-0030 §4, second table, row UC-1.1: what version 2 of the definition asks and the
  amendment, written before the owner answered DEC-0041.
- The owner's answer of 2026-10-01 (DEC-0041): bringing a use case up to his own definition is
  mode 2.
- The use case's named test, `test_the_resolver_places_the_event_and_completes_it_as_the_operator`,
  is untouched: the condition is new, the built part unchanged.

## 3. What was considered

- **Leaving "not identity" as written** and only adding the condition. Rejected: the section
  would then exclude what section 2 requires.
- **Waiting for DEC-0030.** Rejected: the owner moved restoration out of that question; waiting
  would keep a requirement short of his definition with nobody left to answer it.

## 4. Which entry permits it

M2.7: bringing a use case up to the owner's own definition (DEC-0041). The amendment adds
nothing the definition does not ask; a requirement beyond it would be M3.15 and stays in
DEC-0030.
