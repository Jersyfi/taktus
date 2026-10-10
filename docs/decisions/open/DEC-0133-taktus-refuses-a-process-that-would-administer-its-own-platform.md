# DEC-0133 — Taktus refuses a process that would administer its own platform

**Category:** NON-BLOCKING
**Raised in:** the pull request that brings ADR-0052, while checking issue #83 again as P-02 would
**Issue:** [#179](https://github.com/Jersyfi/taktus/issues/179)
**Needed by:** before #83 is built; the roadmap places it in `0.2.0`
**Provisional answer:** Option A, which binds any session that builds #83 before the answer. Marked here and in #83.

## 1. What this is about

Taktus has a rule: an instance never runs on infrastructure it can change itself. If it could,
one wrong step could break the ground it stands on, and nothing would be left to repair it.
Today the person who installs an instance keeps that rule by hand. The roadmap says that from
`0.2.0` Taktus refuses, while planning, a process that would give it such power.

A process names the credentials its steps use — a repository token, a model key — by a name only.
Nothing says what a credential can change. ADR-0052, written with this request, closes that gap:
the operator tells the instance which platform it runs on, and declares for every credential which
platforms it can administer. Taktus then refuses a process whose steps name a credential that can
administer its own platform.

One question is left that the design cannot answer: what happens with a credential the operator
declared nothing about.

## 2. Why you are being asked

Entry M3.15 of `docs/decisions/anchors.taktus.md`: what a use case requires is yours. No use case
requires the refusal today; UC-7.3 names the rule as ADR-0025's and states no condition.

**Sources checked:** the vision (principle 6, no bus factor of zero; principle 10, the whole
autonomy range with guardrails; principle 12, production-ready), ADR-0013 C (repair without
Taktus), ADR-0025 and its *Where this promise ends*, ADR-0052, UC-7.3, UC-1.3 and UC-10.2, both
anchor pages (`anchors.md`, `anchors.taktus.md`) and the register (DEC-0023 and DEC-0024 applied
ADR-0025 to one deployment; none decides what planning must refuse). The direction is clear — the
rule must hold — but not how strict the requirement is about a credential nobody declared.

## 3. What you must decide

Does UC-7.3 require the refusal, and is a credential without a declaration refused too?

## 4. What you need to know to decide

**The proposed condition**, added to UC-7.3 §2:

> - Once an instance names the platform it runs on, a process version whose steps name a
>   credential declared to administer that platform is refused at registration, and a run of it at
>   admission, naming the step, the credential and the platform (ADR-0025, ADR-0052). A credential
>   the operator declared nothing about is refused the same way.

and in §3 the sentence "That an instance never holds credentials for the infrastructure it runs on
is ADR-0025's" becomes: **Not what a credential can really do.** The refusal is as true as the
operator's declaration.

- **The cost of refusing undeclared credentials:** the operator writes one line per credential
  once — `none` for the repository token, the model key, the coding agent's key. For this project
  that is about five lines. A process that names a credential nobody declared stops at
  registration and says which.
- **The cost of admitting them:** nothing to write; a credential that can change the platform but
  was never declared runs, and only a report says it was never looked at.
- **While an instance does not name its platform**, nothing is checked under any option, and the
  instance says so at start.

## 5. Options

### Option A — refusal required; an undeclared credential is refused (recommended)

- **Meaning:** the condition above, as quoted.
- **Consequence:** the rule holds for every credential someone looked at, and a credential nobody
  looked at cannot be used. The install declares this project's credentials.
- **Effort:** #83 as described in ADR-0052; one declaration per credential in the operator's
  configuration.
- **Reversibility:** cheap.
- **Why recommended:** strict in substance and sparing in ceremony (DEC-0039): the rule protects
  the ground repair stands on (ADR-0013 C), and its cost is one line per credential, written once.

### Option B — refusal required; an undeclared credential is admitted and reported

- **Meaning:** the condition without its last sentence; the registration's result and
  `taktusctl` list undeclared credentials.
- **Consequence:** no declarations are needed to start; the rule holds only where someone declared.

### Option C — no condition; the rule stays with the person who configures an instance

- **Meaning:** UC-7.3 stays as it is; #83 closes as not needed in `0.2.0`; ADR-0052 is withdrawn.

## 6. What is blocked

Nothing waits: #83 can be built on the provisional answer. If no answer arrives before it is
built, Option A binds it; under Option B later, one check is relaxed.

## 7. How to answer

"DEC-0133: Option A.", "DEC-0133: Option B." or "DEC-0133: Option C." in the issue. A free-text
answer is read back as an interpretation and confirmed before it is acted on.
