# NTC-0051 — UC-7.1: from level 3, only verified adapters

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-09
**Raised in:** [#132](https://github.com/Jersyfi/taktus/pull/132)
**How it follows:** the owner's project definition, version 2, chapter 5.3: connectors and worker adapters carry a maturity — experimental, verified, reference — and production processes from autonomy level 3 (UC-7.1) may only use adapters from *verified*. The definition's open question 5 asked whether the threshold should be level 3 or level 4, and `docs/vision/history.md` records the answer: kept at *verified* from level 3. The amendment writes that rule into the use case of autonomy levels and adds nothing beyond it.

## 1. What was decided

`docs/usecases/governance/UC-7.1-the-autonomy-range.md` gains a requirement in section 2: a process
at level 3 or above uses only adapters at *verified* or above; a step that only an adapter below
*verified* could serve is not run on it, and the finding names the step and the adapter. "Proven so
far" says the threshold is not built. Section 4 names its sources.

## 2. The evidence

- Definition version 2, chapter 5.3, and open question 5, as quoted above.
- `docs/vision/history.md`, the table of open questions: "The maturity threshold for autonomy level
  3 — Kept at *verified* from level 3."
- `docs/architecture/contracts.md` §3 and `contracts/worker/v1/README.md` state the rule; no use case
  required it. The new UC-14.1 and UC-8.8 point to UC-7.1 for it.
- Nothing is *verified* today: the maturity record of the `catalog` component derives *verified*
  from both halves, and the conformance half is not recorded yet (`docs/architecture/contracts.md`
  §3). The amendment requires; it claims nothing built.

## 3. What was considered

- **Writing the rule into UC-14.1 alone.** Rejected: the rule covers workers, connectors and models
  alike, and it is a rule about what an autonomy level permits.
- **"A process at level 3 with such an adapter does not register."** Rejected: which adapter serves a
  capability is configuration and can change after registration; the definition's "may only use" is
  held where the step runs, which is the reading that adds least.
- **Asking it in DEC-0082.** Rejected: the definition asks for it and the vision's history records
  the owner's answer to the one question about it.

## 4. Which entry permits it

M2.7, *"Bringing a use case up to the owner's own definition: an amendment of what a use case
requires that only restores what `docs/vision/` and the owner's project definition already
require."* The amendment restores chapter 5.3 of the definition, as the vision's history records it,
and adds nothing beyond it.
