# NTC-0017 — UC-8.9: a process leaves as one package, skills included

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-01
**Raised in:** [#52](https://github.com/Jersyfi/taktus/pull/52)
**How it follows:** the owner's project definition, version 2, UC-8.9: every process can be exported as one coherent package, skills included. Section 2's export condition named definition, prompts, configuration and instructions as files; it now names the skills too, and one package per process.

## 1. What was decided

`docs/usecases/catalog/UC-8.9-changing-a-vendor-breaks-nothing.md`, section 2: "Everything that
defines a process — the definition, its prompts, its configuration, its instructions — can be
taken out of Taktus as files in an open format" became "Everything that defines a process —
definition, prompts, skills, configuration, instructions — can be exported as one package per
process, in an open format, and read without Taktus".

## 2. The evidence

- DEC-0030 §4, second table, row UC-8.9.
- The owner's answer of 2026-10-01 (DEC-0041).
- None of the use case's six named tests is touched; they prove the removal test, and the
  export does not exist yet.

## 3. What was considered

- **Files, as before, with the skills added.** Rejected: the definition asks for one coherent
  package; loose files are what an export is meant to replace.
- **A package for the whole instance.** Rejected: the definition asks per process, and a process
  must be able to leave alone.

## 4. Which entry permits it

M2.7: bringing a use case up to the owner's own definition (DEC-0041). The amendment adds
nothing the definition does not ask; a requirement beyond it would be M3.15 and stays in
DEC-0030.
