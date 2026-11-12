# ADR-0289 — A domain is instantiated as a plan in dialogue, and its commissioning instantiates the governance domain

**Status:** accepted · extends ADR-0237, ADR-0259, ADR-0263 · UC-15.1, UC-15.5, UC-1.2

## Context

A domain blueprint is instantiated in dialogue (ADR-0263). The catalogue's `DomainInstances`
keeps the answers: a tool per capability, the processes left out, the owner. Its dialogue was a
list of questions, and `propose` made the proposals once none was open.

Two records stood beside it, unjoined:

- **The plan dialogue** (ADR-0237, UC-1.2) is how Taktus works out anything with a person. A plan
  draft names its four parts, refuses commissioning while one is missing, and records the
  commissioning as an act. UC-15.1 §2 asks that instantiation run as such a plan.
- **The governance domain** (ADR-0259, UC-15.5) is the record of a domain with its one owner, its
  jurisdiction and its processes. Registration refuses to raise a process of a domain without an
  owner. The instance named its owner, but no governance domain was made from it.

## Decision

### 1. An instance opens a plan draft

Starting an instance opens a plan draft for it. The composition root fills what the blueprint
says:

- the goal: the domain, the blueprint and its version;
- one step per kept process with a bundle: method `rule`, the capabilities its bundle calls, and
  its starting level (ADR-0263 §3) in its reason; a proposal is made by a rule;
- an estimate for each step of none, with its basis: a proposal consumes no work;
- the autonomy level, the lowest starting level of the kept processes, with the blueprint's
  reason;
- the result: new process versions.

The draft carries a **domain part**: the instance, the blueprint, and the questions the instance
has open, in the words they ask. The questions stay the instance's; the catalogue still computes
them. A question open is a part the draft lacks.

### 2. Every answer is a revision

An answer — a tool, a process left out, the owner, the jurisdiction — is taken by the instance
and then revises the draft: the open questions and the kept steps are written again as a new
version. The guided mode asks the first open question, then the date the plan is due.

The jurisdiction is a question of the instance: the governance domain needs it (ADR-0259 §1).

### 3. Commissioning the draft is the instantiation

Commissioning the current version is refused while a part is missing, an open question among
them, and the refusal names each. Then, as the person who commissions:

1. the governance domain is instantiated: the instance's domain, its owner, its jurisdiction,
   and the processes of the steps. Where the tenant has a domain of that identifier already,
   commissioning is refused and names it. A refusal by governance stops here: the plan is not
   commissioned and nothing is proposed.
2. the plan is commissioned, recorded `plan.commissioned`;
3. every kept process is proposed at level 2 or below (ADR-0263 §3). A person commissions each.

The instance records the plan and the governance domain it fed. `propose` on its own is
refused once an instance has a plan: there is one way to instantiate.

## Alternatives

- **Keep the question list and record a plan after it.** The plan would be a copy of a dialogue
  that happened elsewhere. UC-1.2's refusals would not hold during it.
- **Let governance read the catalogue's instances.** Two components would hold one domain's
  owner. When the owner leaves (UC-15.5) they would disagree.
- **Ask the jurisdiction in governance after the proposals.** The proposals would exist for a
  domain that could still be refused.

## Consequences

- `command/domain/model/planning.py`: `DomainPart` on the draft; its open questions are missing
  parts. `guided.py` asks them.
- `catalog`: `DomainInstance` gains `jurisdiction`, `plan` and `domain_record`; the question
  `jurisdiction`.
- `composition/domain_blueprints.py`: `DomainDialogue`; `taktusctl domain` acts through it.

## Where this promise ends

- **One domain per instance.** The governance domain takes the instance's domain name, made an
  identifier. A second instance of a domain the tenant has is refused at commissioning; joining
  it to the first is a person's act in governance.
- **Proposals, not versions.** Commissioning the plan makes proposals; each process is still
  commissioned by a person (ADR-0263 §3).
- **No run of the plan.** The plan's steps are proposals. Nothing of the plan runs as a run.
- **A later version is offered as before** (ADR-0263 §4), outside the plan.
- **The owner's leaving is governance's.** Once instantiated, the owner is changed and vacated
  in the governance domain (UC-15.5); the instance keeps the owner it was instantiated with.
