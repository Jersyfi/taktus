# NTC-0262 — UC-4.25: a step that reads text is proposed a move through an embedding

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-11-04
**Raised in:** branch `concept/package-e--quality` (package E, concept mode, DEC-0222, DEC-0227)
**How it follows:** the owner accepted the roadmap's `0.4.0` ("training, evaluation, embeddings, classical ML") and its completion criterion — a step moved from a language model to a trained model on Taktus's own proposal — and issues #210 (embeddings on the ML bench) and #218 (the move, measured). Every language-model step of a process Taktus runs reads text, so the criterion needs embeddings. UC-4.24 excludes neural models and embeddings by name, with #210. No use case required a step that reads text to become a candidate. UC-4.25 states it, with its conditions made observable.

## 1. What was decided

UC-4.25, *A step that reads text is proposed a move through an embedding*, component `process`,
version `0.4.0`, the number package E gave this area. Its three requirements: text is embedded
reproducibly by the ML bench, on an ordinary processor; what a step read as text is learned from,
held to every other floor of UC-4.24 unchanged; what is served is what was evaluated, the
embedding carried in the pinned model file. ADR-0183 builds them.

Concept mode lets a new use case be written beside its implementation (DEC-0222). It was.

## 2. The evidence

- `docs/roadmap.md`, `0.4.0`; issues #210 and #218; DEC-0164 (UC-4.24), DEC-0226 (the
  accelerator is a tenant's, in the owner's comment on #210).
- `docs/architecture/methods.md` §1, the row `neural`: embeddings, reproducible at a pinned
  version and seed.
- `docs/vision/non-goals.md`: no foundation models.

## 3. What was considered

- **Amending UC-4.24.** Rejected: its requirement sections are the owner's words of DEC-0164, and
  its boundary excludes embeddings; a requirement beyond it is a use case of its own.
- **A pretrained sentence encoder.** Rejected in ADR-0183: a library outside DEC-0161 and a
  foundation model by the non-goals' reading.

## 4. Which entry permits it

M2.7, *bringing a use case up to what the owner has already accepted*: here the roadmap's
`0.4.0` and the issues it named. The owner may veto it within seven days of the pull request.
