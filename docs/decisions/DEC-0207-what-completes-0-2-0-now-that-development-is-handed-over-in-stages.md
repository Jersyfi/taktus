# DEC-0207 — What completes 0.2.0, now that development is handed over in stages

**Category:** NON-BLOCKING
**Mode entry:** none fits: M1.7 leaves a milestone's scope to the session, not its completion criterion, which the owner set; the money figure is M3.10
**Raised in:** the pull request that records DEC-0206, while rewriting #87 to the stages of DEC-0197
**Issue:** [#483](https://github.com/Jersyfi/taktus/issues/483)
**Needed by:** 2026-10-23

## 1. What this is about

The roadmap says `0.2.0` is complete when Taktus maintains its own repository for 14 days with no intervention in execution. Since DEC-0197, development is handed to Taktus in stages, each earned by measures. Fourteen days in which Taktus does all the work is stage 3 of that table, "a whole milestone, in the order P-01 computes". Stage 0 runs now. As written, `0.2.0` therefore stays open until stage 3 has been reached, which is weeks or months away. The figure stage 0 is measured against, the money per merged pull request, was left "agreed" and has no value yet.

## 2. Why you are being asked

A milestone's completion criterion is the owner's: M1.7 gives the session the scope of a milestone, because the criteria are fixed. The figure is a limit (M3.10).

**Sources checked:**

- the vision: principle 10 (the whole autonomy range, with guardrails) says nothing of the pace;
- ADR-0039 and ADR-0097: levels and stage 0's mechanics, not when a milestone is complete;
- both anchor pages: M1.7 covers scope, and no entry lets a session change a completion criterion;
- the register: DEC-0197 sets the stages but not which milestone each completes, and DEC-0206 lets the session rewrite #87, not the roadmap.

## 3. What you must decide

Which stage completes `0.2.0`, and the money per merged pull request below which stage 0 counts as met.

## 4. What you need to know to decide

- **Stage 0 so far** (2026-10-14 to 2026-10-16):
  - 8 tasks handed over, 5 pull requests merged (#452, #461, #462, #463, #470).
  - One of them was touched by hand: #470's description failed its check on an ellipsis (#471).
- **Money:** P-03's coding steps cost USD 13.64 in priced runs, and one run before pricing used 17.4 million input tokens, about USD 10. That is USD 2.70 per merged pull request without that run and about USD 4.70 with it. The cheapest merged one cost USD 0.62, after the workspace checks of ADR-0100.
- **The research of 2026-10-14** found about USD 12 per merged pull request before the cost limit and the workspace checks.
- **What `0.2.0` otherwise holds:** everything else on its list is built or closed, except #458 (a halted run resumed with a raised limit) and #74 (the live run of the budget, which DEC-0206 starts now).

## 5. Options

### Option A — `0.2.0` completes with stage 1; the 14 days move to stage 3's milestone (recommended)

- **Meaning:** `0.2.0` is complete when stage 0 has met its measures and stage 1 has then run two weeks within them. Stage 0's measures are 10 handed tasks, at least 80 % merged without rework, and at most USD 3 per merged pull request. The sentence "14 days with no intervention" moves to `0.6.0` (level 4), where stage 3 belongs.
- **Consequence:** `0.2.0` can complete about two to three weeks from now, by measures already being taken.
- **Effort:** the roadmap's two sentences and #87, which this pull request already rewrote.
- **Reversibility:** a later answer moves the sentence back.
- **Why recommended:** it keeps what DEC-0197 chose, every stage earned by numbers, and gives each milestone a criterion it can reach. USD 3 sits between what stage 0 has cost and the cost limit of USD 5 per run.

### Option B — keep the 14 days in `0.2.0`

- **Meaning:** `0.2.0` stays open until Taktus has done all the work for 14 days, that is, stage 3.
- **Consequence:** `0.2.0` stays open for weeks or months, and `0.3.0` and later milestones complete before it.
- **Effort:** none now.
- **Reversibility:** any time.

## 6. What is blocked

Nothing is blocked: work continues on Option A. The roadmap's sentence waits for the answer.

## 7. How to answer

In #483: "DEC-0207: Option A" or "DEC-0207: Option B", or a figure other than USD 3.

## Outcome

**Decided:** 2026-10-16
**Answer:** Option A. "DEC-0207: Option A, mach weiter" (the owner's words: Option A, go on).
**Reasoning given:** none beyond the recommendation.
**What it changes:**

- `0.2.0` is complete when stage 0 has met its measures and stage 1 has then run two weeks within them.
- Stage 0's measures are 10 handed tasks, at least 80 % merged without rework, and at most USD 3 per merged pull request.
- The 14 days with no intervention move to `0.6.0`.
- `docs/roadmap.md` and #87 say so.

**Recorded in:** this pull request
