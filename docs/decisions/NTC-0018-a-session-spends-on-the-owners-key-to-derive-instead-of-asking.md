# NTC-0018 — A session spends on the owner's key to derive instead of asking

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-01
**Raised in:** [#51](https://github.com/Jersyfi/taktus/pull/51); recorded in [#52](https://github.com/Jersyfi/taktus/pull/52)
**How it follows:** CLAUDE.md §9, "Derive before asking", says a question the session can answer from what it has is not asked; the owner had provided the model key under NEED-0003 for exactly this endpoint, so measuring the endpoint with it answered the question inside the purpose the key was given for. Between spending a few calls and asking, the stricter option in substance is the measurement, because it yields the endpoint's actual behaviour rather than an assumption; it is also the one with less ceremony.

## 1. What was decided

The output limit a model step may rely on was **derived by measuring, not asked of the owner.**
A session ran check M-03 of the model contract — does the endpoint stop at the output limit it
is given — against this tenant's model endpoint, with the key the owner provided under
NEED-0003. That was **two calls of a few tokens each, under one cent in total**, billed to the
owner's account. The endpoint held the limit, and `tools/first_run.sh` now runs the same check
before every run, so the limit is declared `hard` only where the endpoint is seen to hold it.

It is recorded because it is a precedent: a session spending money on a credential the owner
provided, without asking first.

## 2. The evidence

- The owner, in the brief of 2026-10-01: the spend "was right", and it is to be recorded as a
  notice because it is a precedent.
- Commit `25b5963` of #51: the derivation in `tools/first_run.sh` and the result, passed live on
  2026-10-01.
- NEED-0003, sections 1 and 2: the endpoint and its key were provided so that Taktus may ask the
  endpoint; checking what the endpoint does with a limit is asking it.
- The alternative was the question it replaced: in #51 the output limit had first been written
  as something the owner should state — an owner action the owner had already rejected as a
  pattern (DEC-0039).

## 3. What was considered

- **Asking the owner for the limit.** Rejected: the owner cannot know it better than the
  endpoint can show it, and the question would have cost his reading time for a figure the
  endpoint gives for under a cent.
- **Reading the limit from the provider's documentation.** Rejected as the only source: a
  document says what a provider promises, not what this endpoint does; M-03 exists because the
  two can differ.
- **Running the full model suite.** Rejected: only M-03 answered the question; every further
  call is spend without a reason.

## 4. Which entry permits it

None does: the anchor pages say nothing about a session spending on a credential the owner
provided. The decision follows the vision and the doctrine — derive before asking (CLAUDE.md §9),
cost control (principle 8) — and is therefore an `unlisted` notice under M2.6.

## 5. The entry it proposes

**M2.8, kind `spend`** — spending on a credential the owner provided, **within the purpose the
needs request names**, to derive what would otherwise be asked: a check, a measurement, a
rehearsal call. The notice states the amount. Bounded: a spend of more than one euro for one
derivation, a spend that recurs without a run that needs it, or a spend outside the purpose the
credential was provided for is not this entry; it is a limit, M3.10, and asked.

**Accepted** by the owner on 2026-10-07 with a different bound (DEC-0049): M2.8 caps the spend at
USD 1 per task, not one euro per derivation.
