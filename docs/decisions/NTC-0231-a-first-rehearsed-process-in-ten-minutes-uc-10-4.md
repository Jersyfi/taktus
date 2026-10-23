# NTC-0231 — UC-10.4: a first rehearsed process in ten minutes, measured

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-23
**Raised in:** [#615](https://github.com/Jersyfi/taktus/pull/615)
**How it follows:** the owner accepted W4 of DEC-0195 on 2026-10-13: a first process in ten minutes, measured, in `0.5.0`. The roadmap's `0.5.0` names it in its completion criterion: "a person new to Taktus reaches a first rehearsed process in ten minutes". Issue #405 states its verification conditions. No use case required it: UC-10.3 asks for a first automation by people who are not technical, but names no time, no rehearsal and no gallery, and belongs to `0.6.0`. UC-10.4 states W4 as a requirement, with the conditions of #405 and what follows from them.

## 1. What was decided

UC-10.4, *A first rehearsed process in ten minutes, measured*, component `command`, state
`specified`, version `0.5.0`. Its conditions are those of issue #405, made observable, and four
that follow from what the owner already accepted:

- after the one install command the person types no further command, because #405 speaks of a
  person without technical knowledge, and every later step is the web app's;
- the process begins at autonomy level 1 or 2, with its reason (ADR-0026, UC-10.3);
- the process goes live only by commissioning after its rehearsal (UC-1.10);
- the report names no person, and no figure assesses the one who took part (principle 14,
  ADR-0015).

The clock starts when the install command is started, not when the instance is ready. That is
the strict reading of "from installing Taktus to a first rehearsed process" in #405. Whether a
build of the image fits inside the ten minutes is what the measurement shows, not what the use
case assumes.

## 2. The evidence

- DEC-0195 §4, W4, and the research it rests on (`docs/research/2026-10-13-warp-review.md` §5).
- `docs/roadmap.md`, `0.5.0`, *Complete when*.
- Issue #405, *How it is verified* and *Where the boundary lies*.
- UC-10.3 §2 and its version `0.6.0`; UC-1.10 §2.

## 3. What was considered

- **Amending UC-10.3.** Rejected: UC-10.3 is a trial of the whole guided start with three people
  in `0.6.0`; W4 is one path, timed, in `0.5.0`. Folding them together would move one of them to
  the wrong milestone.
- **Starting the clock when the instance is ready.** Rejected: it would leave out the part a
  person new to Taktus waits through first, and #405 measures from installing.
- **No use case, the issue alone.** Rejected: the issue closes; the requirement must outlive it.

## 4. Which entry permits it

M2.7, *bringing a use case up to what the owner has already accepted*: here a feature the owner
accepted in DEC-0195, and the roadmap's completion criterion. The owner may veto it within seven
days of this pull request; a veto turns it into a request under M3.15.
