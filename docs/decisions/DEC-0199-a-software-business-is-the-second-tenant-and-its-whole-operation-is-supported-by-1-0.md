# DEC-0199 — A software business is the second tenant, and its whole operation is supported by `1.0.0`

**Category:** NON-BLOCKING
**Mode entry:** M3.2 (accepting the business's catalogue as the feature Taktus proves itself on, with its milestone criteria); who the second tenant is was the owner's own question in DEC-0195
**Raised in:** NEED-0027 and DEC-0195 E4; recorded in the pull request of its own that records the answer
**Issue:** none; the owner answered in conversation, and this record is the question with the answer
**Needed by:** 2026-10-31
**Written after the answer:** the owner answered in conversation on 2026-10-14; the record was written from it; left out of the acceptance rate (DEC-0042).

## 1. What this is about

NEED-0027 asked for the complete use case of a real business by 2026-10-31. Otherwise the
owner's household administration would have become the second tenant (DEC-0195, plan B).

On 2026-10-14 the owner received it. It is a catalogue for operating a small software company:
a web and a mobile app, a cloud backend, subscriptions, private and business customers, and
agents in support and development. It has eleven areas and 96 use cases. Each use case names
its trigger, what the agent does, what a person decides, and a target autonomy stage. The
catalogue also has:

- four autonomy stages and a rule for rising and falling between them;
- a path in six stages, from a daily report to a company that runs without staff in normal
  operation;
- a list of what stays with a person at every stage;
- thirteen requirements on the tool that carries it.

It does not name the systems the business uses, nor how many cases arrive.

## 2. Why you are being asked

Who the second tenant is was yours to answer (DEC-0195 E4). Accepting a feature and changing a
milestone's completion criterion are yours too (M3.2).

**Sources checked:** `docs/vision/` (principles, non-goals), `docs/roadmap.md`, DEC-0195,
NEED-0027, ADR-0092, both anchor pages. None of them chooses the second tenant or says what
`1.0.0` owes it.

## 3. What you must decide

Whether this business is the second tenant, and what Taktus owes its use case by `1.0.0`.

## 4. What you need to know to decide

The catalogue's areas: infrastructure and cloud cost, the budget for models and outside
services, customer service, the quality of the support agent, back office, revenue and billing,
development, release and deployment, product and growth, administration and compliance, and the
steering of the agents themselves.

Development is one area of eleven. The rest is the operation DEC-0195 asked for: exact amounts,
payments a person releases, legal duties, and steps that can mature from a language model to a
trained model.

## 5. Options

### Option A — the business is the second tenant, and `1.0.0` carries its whole use case (recommended)

- **Meaning:** plan B does not start. Every use case of the catalogue, and the way it is
  introduced, is supported by `1.0.0`.

### Option B — the business becomes the third tenant, as NEED-0027 foresaw for a late arrival

- **Meaning:** plan B starts on 2026-11-01; the business follows. It arrived in time, so this is
  not needed.

## 6. What is blocked

Nothing. #400 waits for the systems and the volumes (NEED-0028).

## 7. How to answer

In conversation.

## Outcome

**Decided:** 2026-10-14
**Answer:** Option A. "ich denke die Beschriebung an sich was verlangt wird kann bestmöglich
verwendet werden, dass wir diesen Anwendungsfall bis 1.0 vollständig supporten und auch den
Übergang für den Anwendungsfall wie beschrieben mit abdecken können." and "Das ist der
Anwendungsfall an dem sich Taktus beweisen muss und ansonsten scheitert." (the owner's words:
the description is to be used so that Taktus fully supports this use case by `1.0.0` and also
covers the transition as described; it is the use case Taktus must prove itself on, or fail.)
**Reasoning given:** the catalogue describes directly how the software is introduced step by
step into an existing operation.

**How the session reads the answer.** The owner may correct any point; the next session records
the correction first.

1. **The second tenant.** The business is the second tenant. Plan B of DEC-0195 does not start
   on 2026-11-01. #400 starts with this business.
2. **"Fully supported by `1.0.0`".** `1.0.0` is complete only when every use case of the
   catalogue runs as a process of the tenant in production. Each must also have reached its
   target level, or Taktus has proposed the raise with the evidence the rule asks for. A person
   of the business may decline a raise; that is the business's right. Failing to earn the
   evidence is Taktus's failure.
3. **"The transition".** The catalogue's six stages are a requirement (UC-9.6). Each stage
   begins only when the previous one measurably holds. They are placed on milestones: stage 0
   at `0.4.0`, stage 1 at `0.5.0`, stages 2 and 3 at `0.6.0`, stage 4 at `0.7.0`, stage 5 at
   `1.0.0`.
4. **Stages and levels.** The catalogue's stages A0 to A3 are Taktus's levels 1 to 4
   (`docs/usecases/AF-03-software-operations.md` §3).
5. **What stays with a person.** The catalogue's list becomes the tenant's anchor set. Taktus
   keeps it whole. The business may add to it.
6. **The missing systems.** Processes name capabilities, never products (CLAUDE.md §6). The
   business names a system for each capability. The volumes and roles come with it. That is
   NEED-0028.
7. **What enters this repository.** The catalogue itself does not. The repository carries what
   Taktus must do, in its own words. It names nothing of the business, no system, no amount and
   no person (NEED-0027 §5).
8. **Principle 14.** One use case audits privileged actions, including access "outside working
   hours". It is read as a rule over an organisation-wide window applied to the action. A
   learned pattern of a person's behaviour is forbidden (`docs/vision/principles.md` §14), and
   the vision is binding.
9. **The second domain.** Incoming invoice to payment release (#402) is two use cases of this
   catalogue. #402 is carried at this tenant. It stays at `0.7.0` and still waits for DEC-0029.
   The `it-operations` blueprint (#95) stays at `2.0.0`. The infrastructure use cases this
   tenant needs are part of UC-03, not of that blueprint.

**What it changes:**
- the blueprint-level use case UC-03 and the blueprint `software-operations`;
- nine function-level use cases for what no use case required yet (NTC-0210);
- the completion criteria of `0.4.0` to `1.0.0` and the handover path's stage S3;
- NEED-0027 provided by way 1; NEED-0028 raised;
- #400, #401 and #402 point at this tenant; issues for every new requirement and stage.

**What it does not change:**
- the vision, the non-goals and the principles;
- the project's own development with P-01 to P-03;
- DEC-0029, which must still be answered before `0.7.0`.

**Recorded in:** [#442](https://github.com/Jersyfi/taktus/pull/442)
