---
id: UC-7.4
title: The decision request
component: decision
epic: E7
serves: [P9, P10, P11, P14]
state: specified
version: 0.2.0
tests: []
adrs: {ADR-0008: e6a4e033abd4, ADR-0015: 3a42705e5561, ADR-0017: c932691e9072}
supersedes: null
---

# UC-7.4 — The decision request

## 1. What must be achieved

A process runs unattended while its direction stays with a person. When a run reaches an act that
is a person's — under an anchor, or a question the process cannot answer itself — it halts at the
step boundary and asks. The question is not an alarm: it is a planned, expected question in normal
operation, with a worked answer proposed, and the person can decide it without having followed the
run. Their answer is never acted on before it is understood: Taktus says how it read the answer,
and acts only once the person has confirmed it. Every answer becomes a record that later cases can
be judged by.

## 2. How it is verified

- A decision request has one shape in every process and every channel: the situation, exactly what
  must be decided, the options with their consequences and one recommended with its reason, what is
  blocked, and the date an answer is needed by (ADR-0008, `docs/architecture/governance.md` §3.1).
  A request without a part is not raised.
- Raising one halts the run at a step boundary, never inside a step and never after the act it asks
  about; the run waits in `waiting_human` and resumes at that boundary.
- A free-text answer is not acted on. It is read, its interpretation is sent back in one message,
  and only the confirmed interpretation takes effect. A test answers in free text and finds the run
  still waiting until the confirmation arrives.
- Every answered request produces an entry in the decision register, linked to the run and the
  request.
- Work that waits on an answer is visible in the decider's view and in the run's history; a request
  past its date is shown as such. An unanswered request is never a silent stall.
- How long a decider takes to answer is visible to that decider only by default, and aggregated for
  anyone else by role or department, never by person (ADR-0015).

## 3. Where the boundary lies

**Not escalation.** A fault with a situation package is UC-4.5; a decision request carries options,
not a report of damage (`docs/architecture/governance.md` §3.3). **Not which acts are anchored.**
The anchor set is the tenant's (UC-15.5, ADR-0008). **Not rules from precedent.** Turning a
consistent pattern in the register into a rule, on the person's acceptance, is the roadmap's
`0.6.0`. **Not the repository's register.** How this project asks its owner is ADR-0017, which
applies the same shape by hand; this use case is the product's mechanism.

## 4. What it rests on

ADR-0008, which makes the decision request a domain object beside the strategic anchor; the
contract `contracts/shared/v1/DecisionRequest.json`, which exists; the `decision` component, which
holds requests and the register and has no code yet; the anchors at step boundaries of `0.2.0`;
the protective rule for response times (ADR-0015). This repository already works this way by hand
under ADR-0017 — the register under `docs/decisions/`, the gate on its shape — and that is the
mechanism's first use, not its implementation in the product. Numbered after version 2 of the
definition, in conversation (`NUMBERING.md`); no version of the definition has this use case. Filed
under `decision`, the component that owns decision requests (DEC-0070).
