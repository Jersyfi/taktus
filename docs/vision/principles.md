# The fourteen guiding principles

Not negotiable. Point 1 of the definition of done — *violates no guiding principle* — is checked
against this file.

Each principle carries three things: what it says, **why it exists**, and **what it forbids**.
The third is the operative part. A principle that forbids nothing decides nothing.

---

## 1 — An orchestrator, not another tool landscape

Taktus is the layer above the existing landscape. It conducts tools; it does not become another
tool that has to be maintained.

**Why.** Every automation product eventually grows its own ticket system, its own wiki, its own
dashboard, and the organisation ends up maintaining two of everything. The value of an
orchestrator lies precisely in not being one more thing.

**Forbids.** Building a system of record that an existing tool already provides. Making
anything Taktus produces compulsory. Requiring a Taktus-side object where the organisation's
own system could hold it.

**Watch for.** This is never violated in one large step. It is violated by a convenience added
in a hurry — an incident view, a task list, a document store — each defensible on its own.

---

## 2 — AI at the core

The AI is not a plugin. It plans, decides within its frame, and executes.

**Why.** The alternative — AI as a node in a workflow engine — leaves the human doing the
structural thinking, which is exactly the work worth removing.

**Forbids.** A design in which a person must assemble the process and the AI merely fills
blanks.

**Note.** "AI" here is the whole family, not language models. See principle 8, which is its
counterweight.

---

## 3 — Model- and hardware-agnostic

Any model, any accelerator, any host. No binding to a vendor's hosting.

**Why.** The model layer is the fastest-moving part of the field. A product bound to one vendor
inherits that vendor's roadmap, pricing and politics.

**Forbids.** A product name in the core. A capability available only through one provider. An
assumption that inference happens remotely.

**Checked by.** The architecture test that fails on a product name in the core — the
components, the ports, the shared kernel binding and the wire formats under `src/taktus/` — or
in `contracts/` (`tests/architecture`).

---

## 4 — Tool-agnostic and omnichannel

Repositories, ticket systems, knowledge tools, chat — an open connector framework. Commands
arrive from wherever the person already works.

**Why.** An orchestrator that only works with one vendor's tools is that vendor's feature.

**Forbids.** Referencing a tool by product name in a process, a blueprint or an agent.
Capabilities only.

---

## 5 — Coupled or decoupled control, per process

Process control may sit in Taktus or stay outside it, with Taktus executing. Both are equal,
chosen per process, mixable.

**Why.** Organisations have working processes they do not want to move. Demanding that they
move first is how orchestration projects die before they start.

**Forbids.** A capability available only when Taktus owns the control.

---

## 6 — No bus factor of zero

Complete reporting, maintained documentation, a credentials register, so that a person can step
in and take over completely at any time.

**Why.** This is what makes depending on Taktus rational. Dependence that cannot be dissolved
is a risk; dependence that can be dissolved at any time is a choice.

**Forbids.** A process without maintained handover documentation. A credential only Taktus
knows how to use. Knowledge that exists only inside a run.

**Checked by.** The takeover test (ADR-0013 B): a person can run the process without Taktus.
It is not automated yet; UC-6.3 states what it must show.

---

## 7 — Transparency fitted to the role

Every position sees what matters to it — from the operational detail to the strategic figure.
Freely configurable.

**Why.** Complete transparency does not mean everyone sees everything. It means no one is
denied what they are entitled to see.

**Forbids.** A figure that exists only in one view and cannot be exported. Two numbers for the
same thing.

---

## 8 — Repeatability and cost control

Model use is efficient, reproducible and transparent — without giving up the flexibility that
makes AI useful.

**Why.** This is the counterweight to principle 2. AI at the core is worthless if the result
cannot be relied upon.

It is made real not by avoiding AI but by choosing the method per step and bounding what
each result may be. Four of the eight methods are reproducible, and a step whose result must be
exact may not take it from one that is not. The mechanisms are architecture and are described
there: method selection in `docs/architecture/methods.md` and ADR-0004, exactness classes in
ADR-0014 and ADR-0018, budgets and admission in ADR-0005.

**Forbids.** An `exact` step whose result comes from a variable method: **a number produced by a
language model never reaches the accounting journal.** A step admitted without an estimate. A
budget promise stronger than the provider allows — where a provider makes a limit impossible to
hold, the gap is named where the budget is set, never discovered afterwards.

---

## 9 — Efficiency over verbosity

As little output as necessary, as much as useful. Creativity where the task calls for it.

**Why.** An orchestrator that reports everything is not read, and an unread report is worse
than none — it creates the impression of oversight.

**Forbids.** A report without a reader. Restating the obvious. A notification that carries no
decision and no consequence.

---

## 10 — The whole autonomy range, with guardrails

From *propose only* to fully unattended operation — always with a defined frame, monitoring,
escalation paths and an emergency stop.

**Why.** Level 4 is not a maturity badge and level 1 is not a beginner's setting. The right
level follows from the process, not from the organisation.

**Forbids.** Reserving a level for a size of organisation. Raising a level without a
demonstrated quality history. An autonomy level without a stated reason and without what is
missing to go higher.

**Direction.** Always towards level 4, never forced. A process whose requirements do not allow
it stays where it is, with the reason stated.

---

## 11 — European values and sovereignty

Data protection, EU AI Act conformity, data residency, final human control and transparency as
product features — not as retrofitting.

**Why.** Retrofitted compliance produces a system that can be operated legally and not one that
is trustworthy. The difference shows the first time something goes wrong.

**Forbids.** Sending data outside a configured residency. A compliance claim not generated from
the real configuration. A black-box accounting basis — the weighting table is public and
recomputable from the ledger.

---

## 12 — Production-ready

Usable in business-critical cases: auditability, error handling, restart, permissions, roles,
multi-tenancy.

**Why.** At level 4 Taktus *is* the business-critical path. That is the intent, and it carries
the obligations of any critical system.

**Forbids.** A run that cannot resume after a restart. An audit record that can be altered. A
capability that only works while nothing fails.

**Consequences.** High availability, a documented manual rollback path, and: Taktus must be
repairable without Taktus.

---

## 13 — Freedom instead of vendor lock-in

Models, providers, tools and execution units are interchangeable at any time. Every process,
prompt, configuration and datum is exportable. A decision against a vendor never ends a running
process and creates no migration project — **including a decision against Taktus itself.**

**Why.** This is the promise the product is bought for. It is also the easiest one to erode,
because every shortcut that breaks it saves time today.

**Forbids.** An integration whose removal breaks a process. A format only Taktus can read. A
capability that cannot be reproduced after an export.

**Checked by.** The removal test, weekly, as a process Taktus runs for itself — with the
verdict *broke*, *changed* or *exception* in the ledger. One exception is recorded and
deliberate: the database.

---

## 14 — People at the centre

Taktus takes the monotonous, recurring work so that people can do what brings progress and
satisfaction. It makes the human contribution visible and is **never** used to monitor or
appraise individuals.

**Why.** An orchestrator sees everything that happens in an organisation. The temptation to
turn that into performance data is structural, and a single instance of it destroys the trust
the product needs.

**Forbids.** Any metric that appraises a named person. A ranking of people. A skill containing a
person's behavioural pattern. Integration with a tool of a surveillance character —
keystroke logging, productivity scoring, location tracking — excluded outright.

**Including the owner.** Decision response times are measured, because throughput depends on
them. That analysis belongs to the deciding person and is visible only to them by default.
Aggregation by role or department only.

**Permits, and asks for.** Processes are analysed in every detail — lead time, working time and
the time lost between them, per process, step, role and department — so that wasted time is found
and removed and processes stay economically sustainable. A person sees their own times beside
their role's, and support starts with them. Mistakes are met openly, as something to learn from,
never as evidence against someone (DEC-0123).

**Enforced in the data model, not in a policy.** A feature that violates this is not
misconfigurable — it is unbuildable.
