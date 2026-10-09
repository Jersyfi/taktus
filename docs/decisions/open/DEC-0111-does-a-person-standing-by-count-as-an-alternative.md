# DEC-0111 — Does a person standing by count as an alternative?

**Category:** NON-BLOCKING
**Raised in:** [#PRN](https://github.com/Jersyfi/taktus/pull/PRN), while making #90 ready after #153 enforced the maturity threshold
**Issue:** [#155](https://github.com/Jersyfi/taktus/issues/155)
**Needed by:** 2026-10-23
**Provisional answer:** Option A, marked in #90. The person fallbacks #90 declares are needed under either option — a person must be able to take over every process (principle 6) — so #90 proceeds; only whether they earn *verified* follows your answer.

## 1. What this is about

Since #153, a process at autonomy level 3 runs a step only on an adapter whose maturity is
*verified*. Verified needs two things: the adapter passed its conformance suite, and it passed the
removal test. The removal test withdraws an adapter and looks at what happens to every step that
used it. If nothing serves the step any more, the verdict is *broke*. If something else serves it,
the verdict is *changed* — and *changed* is what passes.

The question is what may count as "something else". Taktus's own development processes, P-01 to
P-03, use the repository connector in seventeen steps, and no second repository connector exists.
If a person who takes such a step over counts, these steps can declare that person, and the
processes can run at level 3 in `0.2.0`. If only a second adapter counts, they cannot, until a
second adapter exists for every capability they use.

## 2. Why you are being asked

Entry M3.15 of `docs/decisions/anchors.taktus.md`: what a use case requires is the owner's. The
two readings are two different requirements of UC-8.9, and the documents disagree about which one
holds.

**Sources checked:** the vision (principle 13, freedom instead of vendor lock-in — removing an
integration must not break a process; principle 6, no bus factor of zero — a person must be able
to take over any process), the ADRs (ADR-0013 B, the takeover test; ADR-0030, the rehearsed
removal test; ADR-0039, the threshold), both anchor pages (M3.15) and the register (NTC-0051,
which wrote the threshold into UC-7.1; NTC-0079). `docs/architecture/contracts.md` §4 says
*changed* is "another adapter or a person serves the step", and the verdict code counts a declared
person. UC-8.9 §3 says "where no second adapter for a capability exists, the verdict is *broke*",
and the roadmap's `0.4.0` made a second coding worker the way to *changed*. None of them settles
which reading the requirement is.

## 3. What you must decide

Whether a step that declares a person as its fallback earns the removal half of *verified* for
the adapter it uses.

## 4. What you need to know to decide

- **A fallback** is what a step names to take over when its method or adapter is unavailable. A
  person as fallback means the run stops at that step and a named role does it by hand, following
  the process's maintained instructions (the takeover test, ADR-0013 B).
- **What level 3 means:** Taktus runs the process without asking at each step; anchors still halt
  it. A step whose adapter is removed would then wait for a person instead of failing.
- **What it commits the project to:** with Option A, every capability can reach *verified* without
  a second product; the removal test then measures whether a person can stand in. With Option B,
  every capability a level-3 process uses needs a second adapter first.

## 5. Options

### Option A — a declared person counts (recommended)

- **Meaning:** a step on an integration that declares a person fallback, with instructions a person
  can follow, makes the removal verdict *changed*. UC-8.9 §3's sentence is narrowed: where no second
  adapter and no person takes the step over, the verdict is *broke*.
- **Consequence:** P-01 to P-03 can run at level 3 in `0.2.0` once #90 and #93 are built; the 14-day
  criterion of `0.2.0` becomes reachable. A second adapter stays the better outcome and remains on
  the roadmap (#154).
- **Effort:** #90 as written: person fallbacks on seventeen steps, a takeover section, a test.
- **Reversibility:** cheap until level 3 runs on it; afterwards, raising the bar stops those
  processes again until second adapters exist.
- **Why recommended:** it is what principle 6 asks for anyway — a person can take over — and it
  keeps principle 13's promise that removing an integration breaks no process, because the process
  continues through the person.

### Option B — only a second adapter counts

- **Meaning:** UC-8.9 §3 stands as written; a person fallback is required for the takeover test but
  does not earn *verified*.
- **Consequence:** P-01 to P-03 cannot run at level 3 until a second repository connector, coding
  worker and model adapter exist; `0.2.0`'s criterion moves behind them, or the three processes are
  lowered to level 2, where every step waits for a confirmation.
- **Effort:** three second adapters, each with its conformance suite.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing waits: #90 proceeds on the provisional answer, and its fallbacks are needed either way.
What depends on the answer is whether P-01 to P-03 may then run at level 3 on their own instance
(#87). If no answer arrives by 2026-10-23, the provisional answer stands; under Option B later, the
removal verdicts those fallbacks earned would be recomputed as *broke*, and the processes would stop
at level 3 until second adapters exist.

## 7. How to answer

"DEC-0111: Option A." or "DEC-0111: Option B." in the issue. A free-text answer is read back as an
interpretation and confirmed before it is acted on.
