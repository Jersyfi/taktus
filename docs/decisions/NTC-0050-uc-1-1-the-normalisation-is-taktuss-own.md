# NTC-0050 — UC-1.1: the normalisation is Taktus's own

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-09
**Raised in:** [#132](https://github.com/Jersyfi/taktus/pull/132)
**How it follows:** the owner's project definition, version 2, UC-1.1: "the normalisation itself is part of the Taktus core (chapter 5.4)"; chapter 5.4: the channel normalisation is thin and part of the control plane, no foreign gateway product forms the core, and channel libraries may be used inside a connector. The amendment writes that as a condition of UC-1.1 and adds nothing beyond it.

## 1. What was decided

`docs/usecases/command/UC-1.1-commands-from-any-channel.md` gains a requirement. Section 1 says
that turning an input into a command is Taktus's own work. Section 2 gains the condition: the
normalisation is part of the `command` component, no foreign gateway or runtime product performs it,
and a library for a channel may be used only inside that channel's connector. "Proven so far" says
how far the architecture tests hold it. Section 4 names chapter 5.4 of the definition.

## 2. The evidence

- Definition version 2, UC-1.1, acceptance criteria, and chapter 5.4, as quoted above. Version 2 added
  both; the use case was written against the earlier version and restored once already (NTC-0014),
  for the identity, context and reply address, not for this.
- `docs/vision/non-goals.md` already says it as a non-goal: no foreign gateway or runtime product as
  the core; channel normalisation, governance and the ledger stay first-party. No use case held it as
  a condition.
- The migration's third step re-read every use case of `command` against version 2 (issue #62).

## 3. What was considered

- **Leaving it to the non-goal.** Rejected: a non-goal is binding, but a use case is where a
  condition is checked, and the definition put this one in the use case.
- **Asking it in DEC-0082.** Rejected: the condition adds nothing the definition does not ask.
  DEC-0041 makes restoring the session's.

## 4. Which entry permits it

M2.7, *"Bringing a use case up to the owner's own definition: an amendment of what a use case
requires that only restores what `docs/vision/` and the owner's project definition already
require."* The amendment restores definition UC-1.1 and chapter 5.4 and adds nothing beyond them.
