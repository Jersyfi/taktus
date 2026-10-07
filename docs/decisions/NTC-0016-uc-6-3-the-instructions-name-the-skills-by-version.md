# NTC-0016 — UC-6.3: the instructions name the skills by version

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-01
**Raised in:** [#52](https://github.com/Jersyfi/taktus/pull/52)
**How it follows:** the owner's project definition, version 2, UC-6.3 and UC-14.2: the takeover documentation names the skills a process uses. Section 2 lists what the instructions name per step; the skills, by version, become the sixth item, and the count the test checks follows from five to six.

## 1. What was decided

`docs/usecases/process/UC-6.3-the-takeover-test.md`, section 2: what the instructions name for
every step gains "the skills the step uses by version", and the test that reads every bundle's
instructions finds all **six** items for every step instead of five.

## 2. The evidence

- DEC-0030 §4, second table, row UC-6.3.
- The owner's answer of 2026-10-01 (DEC-0041).
- The use case is `specified` and names no test; nothing built changes.

## 3. What was considered

- **Naming the skills per process, not per step.** Rejected: the section lists everything per
  step, and a person taking a step over needs the skills that step uses.
- **Without the version.** Rejected: a skill changes between versions, and instructions that
  name a skill without its version describe whichever one is current, not the one the process
  version ran with.

## 4. Which entry permits it

M2.7: bringing a use case up to the owner's own definition (DEC-0041). The amendment adds
nothing the definition does not ask; a requirement beyond it would be M3.15 and stays in
DEC-0030.
