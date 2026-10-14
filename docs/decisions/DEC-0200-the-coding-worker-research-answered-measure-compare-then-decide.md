# DEC-0200 — The coding-worker research answered: measure, compare, then decide

**Category:** NON-BLOCKING
**Mode entry:** M3.10 (a target and a spend), M3.12 and M3.14 (models), M3.2 and M3.15 (features)
**Raised in:** the research of 2026-10-14, `docs/research/2026-10-14-the-coding-worker-and-what-taktus-keeps.md` (#423), §8
**Issue:** none; the owner answered in conversation
**Needed by:** 2026-10-14
**Written after the answer:** the owner answered in conversation on 2026-10-14; left out of the acceptance rate (DEC-0042).

## 1. What this is about

The research's four open questions: a target for money per merged pull request in stage 0
(DEC-0197); a calibration of the coding agent's model; compression of tool output inside the
worker; a writing standard as a product capability.

## 2. Why you are being asked

A target and a spend are limits (M3.10); binding a model is M3.12 and M3.14; a new product
capability and what a use case requires are M3.2 and M3.15.

**Sources checked:** DEC-0197, DEC-0019, DEC-0193, the research's §2 to §7; none sets these.

## 3. What you must decide

The four questions of the research's §8.

## 4. What you need to know to decide

The research's §2 (measured: about USD 12 per merged pull request) and §7 (the staged plan).

## 5. Options

### Option A — the research's recommendation on each question (recommended)

USD 3 per merged pull request; a calibration on fixed cases for at most USD 15; compression
allowed locally, reversibly, recorded and measured; a writing standard shipped as a default.

### Option B — the research's alternatives

As the research's §8 lists them per question.

## 6. What is blocked

Changes 7 to 9 of the research's staged plan.

## 7. How to answer

In conversation.

## Outcome

**Decided:** 2026-10-14
**Answer:** in the owner's words, translated:
1. **Target per merged pull request: Option B, leave it** at the run's limit of USD 5 for
   now.
2. **Model calibration: Option A.** "Taktus should later act wisely with customers here too:
   offer model tests when models are introduced or Taktus proposes one — for example three test
   runs with different models, at one provider Haiku, Sonnet and Opus, and look which produces
   the best output; when switching between providers, test at one level, for example between
   two providers' top models; and the same for a change of model version, for example from
   version 5 to 5.5. This must be decided differently per use case and task."
3. **Compression: Option A,** with an addition: "I am generally for always capturing
   measurements, so that, for the use case Implement for example, one could look at a graph
   that shows from data where in the process how much money was used, where the Takt
   consumption arises, for an llm step the input and output tokens, and what the compression
   saved on the input — what it would have been without it — and a comparison run of the same
   task once with and once without compression, comparing the results and how good they are.
   Only when we can always compare and say, proven, that something is better can we decide for
   it. Full transparency and traceability, quickly understandable, and visual where possible
   and sensible."
4. **Writing standard: Option A,** "a standard is good, but the organisation must be free to
   decide otherwise, so that we keep Taktus's full flexibility."

**Reasoning given:** the owner's: decide only on what is measured and compared; transparency and
traceability for every change; flexibility for each organisation.
**What it changes:**
- The stage-0 measure of money per merged pull request is the run's limit of USD 5 until the
  owner sets another.
- The session runs a calibration of the coding agent's model on fixed cases (#408) for at most
  USD 15, three models of one provider at one level each.
- Model trials before a model is introduced, proposed or changed — within one provider across
  levels, across providers at one level, across versions — become a product capability, raised
  as an issue and specified as a use case (M3.15 accepted here in substance).
- Compression inside the worker is allowed, locally, reversibly, recorded in the provenance and
  only after it was measured; every such change is decided on a comparison run of the same task
  with and without it, the results compared for quality as well as cost.
- Measuring and showing where a process spends — money, Takte, tokens in and out per step, what
  a compression saved, and comparison runs side by side, visually where sensible — becomes a
  product capability, raised as an issue and specified as a use case.
- A writing standard per language ships as a default, which each organisation may replace with
  its own, never emptied.
**Recorded in:** this pull request
