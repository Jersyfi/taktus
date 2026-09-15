# UC-01 — Product development, unattended

Blueprint `dev-orchestration`. Reference case: a software product heading for `1.0.0` and beyond,
whose **direction** a person owns and whose **execution** Taktus carries.

---

## 1. The task in one sentence

Taktus drives development from the roadmap, starts execution units on its own, maintains the backlog
and the milestones, checks continuously for inconsistencies, reports — and stops when a decision
about direction is due, until it has been made.

---

## 2. Eleven processes

| ID | Process | Trigger | Autonomy | Result |
|---|---|---|---|---|
| **P-01** | Roadmap control | daily · roadmap changed | 3 | issues created and updated, milestones assigned, dependencies set |
| **P-02** | Refinement | an issue without acceptance criteria | 3 | an implementable issue: context, criteria, estimate, dependencies |
| **P-03** | Implementation | issue ready **and** capacity free | 4 | branch, code, tests, pull request, links, status |
| **P-04** | Review | pull request opened | 3 | a structured review; merge by policy (CI green, no contract change, no principle violated) |
| **P-05** | Intake and triage | issue · discussion · chat · email | 3 | bug / feature / out of scope / later version — with reasons, otherwise a decision request |
| **P-06** | Consistency check | after every merge · nightly | 3 | drift between docs, ADRs, the API contract, the schema and the implementation → issues |
| **P-07** | Quality reports | weekly | 4 | load test, performance trend, issue and bug statistics, coverage, security findings |
| **P-08** | Decision request | raisable from any process | *anchor* | a chat thread in the fixed shape; the branch blocks until confirmed |
| **P-09** | Milestone report | a version level reached | 4 | what shipped, what stayed open, quality position, next step |
| **P-10** | Repository hygiene | daily | 4 | dependencies, vulnerabilities, stale issues and pull requests |
| **P-11** | Billing | later | 2 | the `finance` blueprint; legal anchors apply |

---

## 3. What is level 4 and what is not

Unattended: **P-03, P-07, P-09, P-10.**

Anything touching *direction* raises a decision request and waits: a scope change · accepting or
rejecting a feature, whether the idea came from the owner or the community · assigning it to a
version · an architectural change with ADR effect · a release · licensing, pricing, public
communication.

That is not a compromise on level 4 but its correct application: **level 4 means unattended, not
unowned.**

The anchor set is configurable. Another organisation running the same blueprint will draw the line
elsewhere, and that is expected.

---

## 4. The shape of a decision request

Identical across every process and every channel:

```
[DR-2026-014] Strategic · due 22 Sep

SITUATION
Two community requests ask for X. The current architecture provides Y for that.
Affected: 3 open issues, 1 ADR.

DECISION NEEDED
Does X go into 0.9.0, into 1.1.0, or not at all?

OPTIONS
A  (recommended) 1.1.0, after the contract freeze.
   Consequence: 0.9.0 stays on schedule. Effort: medium, after 1.0.0.
B  Take it into 0.9.0.
   Consequence: two issues slip, ADR-0031 needs rewriting. Effort: high.
C  Decline — conflicts with principle 1.
   Consequence: a reply to the community is needed.

BLOCKING: #412, #418
```

A free-text answer is followed by **one** message stating the interpretation. Work continues after
confirmation, never on an assumption.

---

## 5. Access

| Where | For |
|---|---|
| **Web app** (laptop and phone, same app) | dashboard, process diagrams with their data, run history, ledger, consumption, bottlenecks, pair editing |
| **Chat** | status questions, decision requests, reports, idea sessions with project knowledge |
| **CLI** | administration, conformance checks, emergency access |

All three produce the same command. An answer always returns to the channel the question came from.

---

## 6. Sessions

Besides processes, this case needs the **chat with project knowledge**: working out ideas, thinking
through alternatives, building a process change together. A session is persistent, bound to a
project, reads the connected knowledge layer (repository, docs, ADRs, decision register, run
history) and can end in either a command or a new process version.

Sessions run in the web app **and** in chat. One session, two surfaces.

---

## 7. Why this is more than a coding session

P-06, the consistency check between version levels, is the reason.

A coding session sees one session. Taktus sees **every run since the first commit**, knows every
entry in the decision register and every check result. Drift between an ADR and its implementation
does not appear within one session — it accumulates over time and is only found over time.

The same holds for P-01: a roadmap is not read once, it is held against the real state daily.

---

## 8. Dependencies

`github` connector (`0.1.0`) · chat connector (`0.2.0`) · decision requests and anchors (`0.2.0`) ·
web app (`0.3.0`) · reports and second tenant (`0.4.0`) · level 4 (`0.6.0`).

This blueprint is **not** pointed at a second production project before `0.4.0`, and starts there at
level 1–2.
