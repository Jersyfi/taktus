# ADR-0225 — *Untried* is said wherever a level is shown

**Status:** accepted · builds on ADR-0180 §3 · closes what its *Where this promise ends* left
open about reports, the chat and the register · serves UC-6.3 · issue #627

## Context

ADR-0180 §3 calls a version **untried** when it runs at level 3 or 4 and no person has passed a
trial of its takeover instructions on it. A *trial* is a person running the process by hand
from those instructions alone. The process level and the overview of the web app said so. Three
other places show a level and did not: the chat, the register of everything that acts for a
tenant (ADR-0147), and the reports about a tenant's stages (ADR-0137, ADR-0191).

## Decision

1. **The chat.** A channel that cannot draw receives a level's text, element by element, as
   the level hands it to the web app (ADR-0069). The process level's text and each process's
   line of the overview already carry *untried*. The chat therefore says it in the web app's
   words, and a named test holds it there.
2. **The register.** Each use of an adapter by a step carries `untried`, read from the trials
   with the rule of ADR-0180 §3 (`ActorUse.untried`). A row whose adapter serves an untried
   process needs attention, with the reason "N process(es) acting on it at level 3 or 4 … untried
   by hand: <processes>". The register names processes, never a person.
3. **The stage reports.** The level a process runs at, as the stages read it, carries whether a
   passed trial exists on its active version (`RunningLevel.tried`). Each process of a stage's
   view carries `untried`: it runs, or would run once the stage opens, at level 3 or 4 without
   a passed trial. The report that proposes opening a stage names each such process, its
   version and the command that records a trial. `GET /stages` returns the field.

## Alternatives

- **Refuse to open a stage while a process is untried.** UC-6.3 asks that the state is seen,
  not that it blocks. A trial is a person's act; a rule that waits for it would make the owner's
  calendar a gate of the software. The report puts it in front of the person who opens the
  stage, who decides.
- **A field of its own in the chat's answer.** The chat is the level's text by design
  (ADR-0069). A second wording would drift from the web app's.

## Consequences

- `ActorUse.untried` and an attention reason in `reporting/domain/service/acting.py`;
  `ActingReads` takes the trials repository.
- `RunningLevel.tried`, `ProcessEvidence.untried`; `LevelsOfTheProcess` takes the trials
  repository, and `stage_wiring` hands it over.
- `GET /stages` and `GET /register` carry the new fields.

## Where this promise ends

- *Untried* says that no trial was recorded. It does not say the instructions are wrong, and a
  recorded trial does not prove them right: a trial records what the person says (ADR-0180).
- The report that a stage stopped holding does not repeat it: a level that fell is at most the
  one it fell to, and the proposal to open the stage again says it.
- A report a process delivers by its own steps says nothing of it unless its step names it.
- Carrying out a trial stays a person's act; for this project's processes it is the owner's.
