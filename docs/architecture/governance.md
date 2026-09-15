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

Level 4 is not reserved for large organisations. A private individual with three daily micro-jobs
has the same claim to it as a corporation.

---

## 2. Anchors

An anchor keeps an act with a person **regardless of the autonomy level of the rest of the process**.
Two classes:

| Class | Occasion | Examples |
|---|---|---|
| **Legal anchor** | legally binding acts | signature · payment release above a threshold · tax filing · termination · data-protection notification · contract conclusion |
| **Strategic anchor** | conceptual and strategic direction | scope · accepting or rejecting a feature · version assignment · architectural change · releases · licensing and pricing · public communication |

**Every organisation defines its own anchor set.** A business at level 4 with a different model will
draw the line somewhere else, and some owners will hand over nearly everything. The set is
configurable per tenant, per domain and per jurisdiction, and it **can be reduced but never
emptied** — an act with legal force always has a person behind it.

An anchor halts the run at a **step boundary** — never before, never after — and raises a decision
request.

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
  class: strategic | conceptual | domain | legal
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

The Taktus project applies the same mechanism to its own repository: which questions reach the
owner is listed in [`docs/decisions/anchors.md`](../decisions/anchors.md), the shape and the return
path are in [ADR-0017](../adr/ADR-0017-decision-requests-in-the-repository.md), and the register is
[`docs/decisions/`](../decisions/README.md).

### 3.3 Against escalation

| | Decision request | Escalation |
|---|---|---|
| Occasion | planned, expected, recurring | fault, frame exceeded, business damage |
| Content | options with a recommendation | situation package: what happened, what was tried, what is affected |
| Urgency | a deadline | a response-time target |
| Outcome | a decision in the register | a fix, jointly or manually |

---

## 4. Limits that do no harm

- **Admission instead of abort:** every step is estimated before it starts and runs only if its
  demand fits what remains. No limit is ever breached — provable from the ledger.
- **Limit health:** Taktus also watches whether limits *themselves* do harm — work queueing
  repeatedly, delayed progress, critical processes held up. It then reports which limit, which
  queue, and which change it recommends, with cost and benefit. **The change is decided by a
  person.**
- **Emergency stop** at any time, globally and per process.

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
