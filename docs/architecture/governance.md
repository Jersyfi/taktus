# Governance

Autonomy is not a switch, it is a frame. This document describes the frame.

---

## 1. The autonomy range

Named after the role a person plays in the agent's decision loop.

| Level | Name | The person |
|---|---|---|
| 1 | Observe and propose (AI in the loop) | decides and executes |
| 2 | Execute after approval (human in the loop) | confirms every step |
| 3 | Autonomous under supervision (human on the loop) | watches reports and samples |
| 4 | Virtual agent business (human out of the loop) | sets frame and goals, is drawn in when the frame is exceeded |

**Levels apply per process, per tool action and per risk class** — not per process alone. That
granularity is not a luxury: a real operating mandate says "roll back automatically, never restore
from backup automatically", and those are two actions inside one process.

**Raising a level** requires explicit approval **and** a demonstrated quality history. Even at
level 4 the emergency stop, the reporting duty and the escalation duty apply in full.

**Every process carries its level with its reason** (ADR-0026): the level it runs at, why, and
what is missing to go one level higher — or what forbids it where the process's requirements
do not allow the next level. The direction is always towards level 4 and never forced. Where
the conditions `toward_next` names are met, Taktus proposes the raise with the evidence; a
person decides. The statement is shown wherever the process is shown.

Level 4 is not reserved for large organisations. A private individual with three daily micro-jobs
has the same claim to it as a corporation.

**How levels 1 to 3 are enforced** (ADR-0039). The statement sets a level per process and, under
`actions`, per tool action: a capability a step requires or a connector operation it calls. A
step runs at the lowest level that applies to it, and the run engine applies it before anything
of the step starts:

| Level | Before a step starts |
|---|---|
| 1 | a step that acts — hands work to a worker, calls an outward operation — is not executed: its proposal is recorded, and it waits until a person reports the act performed; analysis runs |
| 2 | the step waits until a person confirmed it |
| 3 | nothing is asked; the step runs only on an adapter at *verified* or above, and is refused with a finding that names it and the adapter otherwise |

A waiting step holds back only the steps that depend on it; the run waits in `waiting_human` once
nothing else can run. A rehearsal is asked for neither (NTC-0079). A level rises only where a
version is registered: with a person's approval and the quality history — runs in a row without
a failure or a result defect — that the replaced version names under `history`. A refusal is the
ledger entry `autonomy.refused`; Taktus may propose a raise (`autonomy.proposed`) and never
applies one. Level 4 and levels per risk class are not built yet.

---

## 2. Anchors

An anchor keeps an act with a person **regardless of the autonomy level of the rest of the process**.
Three classes:

| Class | Occasion | Examples |
|---|---|---|
| **Legal anchor** | legally binding acts | signature · payment release above a threshold · tax filing · termination · data-protection notification · contract conclusion |
| **Strategic anchor** | conceptual and strategic direction | scope · accepting or rejecting a feature · version assignment · architectural change · releases · licensing and pricing · public communication |
| **Correction anchor** | correcting a result after it has left the system (ADR-0022) | re-issuing an invoice a customer received · re-sending a partner file · restating a value a tax authority holds · retracting a delivered report |

The legal-anchor class above is the project's own list, not legally reviewed for any jurisdiction.
Before any finance or personnel blueprint is used by a tenant, it is reviewed for that tenant's
jurisdiction by qualified reviewers — a tax adviser for the finance acts, a labour-law specialist
for the personnel acts — and the review is recorded with its date and jurisdiction. Every change
to the catalogue and every new jurisdiction is reviewed again. Until then it is marked as not
legally reviewed wherever it is shown (DEC-0029).

The correction anchor has a checkable trigger. A result *has left the system* when the ledger
holds an egress entry for it or for anything derived from it: `egress.write` (a connector wrote
outward), `egress.delivery` (a channel delivered), `egress.read` (an external system read through
Taktus). *Derived from* is the provenance chain read forward. Analysis — detecting a result
defect, bounding it, planning its repair — is never anchored; correction inside the system is not
anchored; correction of anything that has left the system is. The predicate lives in
`src/taktus/components/governance/domain/service/egress.py`.

**Every organisation defines its own anchor set.** A business at level 4 with a different model will
draw the line somewhere else, and some owners will hand over nearly everything. The set is
configurable per tenant, per domain and per jurisdiction, and it **can be reduced but never
emptied** — an act with legal force always has a person behind it, and so does a correction
that reaches a third party.

An anchor halts the run at a **step boundary** — never before, never after — and raises a decision
request.

**In the product** (ADR-0042) a tenant's anchors are a configuration the governance component
keeps: the anchors in the shape of `contracts/shared/v1/Anchor.json`, and the tenant's risk
classes, each a name for a set of tool actions. One that leaves the legal or the correction class
empty is refused; a tenant that configured nothing holds the shipped default, one legal and one
correction anchor decided by the role `owner`. An anchor applies to a step when every selector it
gives matches its tool actions, its process and its risk classes. The run asks before anything of
a step starts, before its autonomy level is applied, and the step waits in `waiting_human` with
one decision request per anchor.

> Full autonomy without responsibility would be a bus factor of zero in another form. Every
> instantiated department has exactly one human owner.

---

## 3. Decision requests

The *planned* question about direction during normal operation — distinct from *escalation*, which
reports a fault. A level-4 process whose direction a person owns needs both.

### 3.1 Shape

```yaml
decision_request:
  id: DR-2026-014
  raised_by: { run: 17342, step: roadmap-consistency }
  class: strategic | conceptual | domain | legal | correction
  situation:        # the problem, briefly
  question:         # exactly what must be decided, as a question
  options:
    - id: A
      proposal:
      consequence:
      effort:
      recommended: true
    - id: B
      ...
  blocking: [issue#412, issue#418]
  channel: { connector: chat, address: ..., thread: ... }
  due: 2026-09-22
  status: open | answered | interpreted | confirmed | applied
  answer_raw:
  answer_interpreted:
  outcome: DEC-0031          # entry in the decision register
```

The shape is **identical** across every process and every channel. The reader should be able to scan
it in their sleep by the third one.

### 3.2 Three rules

1. **Never interpret silently.** A free-text answer is read, turned into a structured interpretation
   and reflected back in *one* message for confirmation ("I read that as option B, but without X.
   Correct?"). It only takes effect after confirmation. No parser that guesses.
2. **Every answered request produces an entry in the decision register** — the counterpart to an ADR,
   but for operating decisions. It is also the precedent memory from which Taktus can later judge
   similar cases itself.
3. **Blocked work is visible.** Whatever waits on an answer appears in the decider's view and in the
   run history. An unanswered request is never a silent stall.

**In the product** (ADR-0042) the `decision` component holds requests and the register. A request
is addressed to the role its anchor names and reached on the control plane's own surface
(`/decisions`, with the decider's account key): listed with what is overdue, answered, its reading
sent back and confirmed. The reading is a rule — the answer names exactly one option, or none is
read — and every answer is confirmed, a chosen option as well as free text. A decider reads their
own response times; anyone else reads them aggregated by role or department over at least two
deciders (ADR-0015).

### 3.3 Against escalation

| | Decision request | Escalation |
|---|---|---|
| Occasion | planned, expected, recurring | fault, frame exceeded, business damage |
| Content | options with a recommendation | situation package: what happened, what was tried, what is affected |
| Urgency | a deadline | a response-time target |
| Outcome | a decision in the register | a fix, jointly or manually |

### 3.4 Four modes

Not every question is a decision request. Every question an operator meets — Taktus at level 3
or 4, or a session working in a repository — falls into one of four modes: the operator decides
without notice; the operator decides and records a notice; the operator prepares a worked
opinion and the owner decides; the owner decides and the operator supplies data. Which
question falls into which mode is the tenant's anchor configuration. The shipped default is
[`docs/decisions/anchors.md`](../decisions/anchors.md), a template a tenant inherits and
adapts. The same anchor may resolve differently per tenant: a change to an accepted
architecture decision is the owner's in a managed product and the operator's in the Taktus
project while the vision holds.

The Taktus project applies the same mechanism to its own repository: its own configuration is
[`docs/decisions/anchors.taktus.md`](../decisions/anchors.taktus.md), the shape and the return
path are in [ADR-0017](../adr/ADR-0017-decision-requests-in-the-repository.md), and the register
— decisions, notices and needs — is [`docs/decisions/`](../decisions/README.md). A *need* is
what the work requires and only the owner can provide — a credential, an account, an access —
and is raised when it becomes foreseeable, not when it blocks
([ADR-0028](../adr/ADR-0028-what-the-owner-must-act-on-becomes-a-record.md)); what is open is
in [`docs/status.md`](../status.md).

---

## 4. Limits that do no harm

- **Admission instead of abort:** every step is estimated before it starts and runs only if its
  demand fits what remains. No limit is ever breached — provable from the ledger.
- **Limit health:** Taktus also watches whether limits *themselves* do harm — work queueing
  repeatedly, delayed progress, critical processes held up. It then reports which limit, which
  queue, and which change it recommends, with cost and benefit. **The change is decided by a
  person.**
- **Emergency stop** at any time, globally and per process — by a person. An *automatic*
  emergency stop, once detection can trigger one (`0.5.0`), is decided by a **rule** over few,
  measurable, documented criteria: the size of the error window, the exactness class affected,
  whether data has left the system, whether a legal anchor lies downstream, the business
  relevance of the process (ADR-0023). Thresholds are tenant configuration; a criterion may be
  added and a threshold changed, but the set cannot be emptied. Only the narrative — the
  incident description, the situation package — may come from a language model, and it names
  the rule and the facts it fired on.

---

## 5. Least privilege throughout

Taktus works with the minimum permissions needed, and that extends to the worker: it receives only
the tools and credentials the process allows, injected at runtime, never stored. Role profiles of
shared agents may only **narrow** the core's permissions, never widen them.

Shared agents run strictly in the permission, credential and cost context of the *calling user*,
never of their author. No user sees another's mailbox, data or secrets.

---

## 6. Principle 14, enforced

Taktus data steers processes and cost, never people.

- No metric assesses a named person.
- The bus-factor index refers to roles and processes, never individuals.
- A person's own relief view belongs to them; aggregation for management is anonymised at process
  level only.
- Response-time analysis for decision requests belongs to the deciding person and is visible only to
  them by default. Aggregation by role or department only. No ranking.
- Skills learn at process level: no skill contains a person's behavioural pattern.
- Tools with a surveillance character are excluded outright by the integration code.

This is a data-model property, not a policy. A feature that violates it is not misconfigurable — it
is unbuildable.

`tests/architecture/test_no_figure_names_a_person.py` holds it: a value type of the core or a
table that holds a quantity beside a field naming a person fails, unless it is a record of one
act without a total, or a read of one's own with the test that proves nobody else reads it
(NTC-0169). An aggregate of the time persons took to answer is withheld where fewer than two
persons answered within it (ADR-0042, NTC-0168).
