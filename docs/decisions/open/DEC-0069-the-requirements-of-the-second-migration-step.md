# DEC-0069 — The requirements of the second migration step

**Category:** NON-BLOCKING
**Raised in:** [#120](https://github.com/Jersyfi/taktus/pull/120)
**Issue:** [#111](https://github.com/Jersyfi/taktus/issues/111)
**Needed by:** 2026-10-22
**Provisional answer:** Option A. The seventeen use cases of the second migration step are in force with the conditions they add beyond version 2 of the definition, and bind any session that builds one of them before the answer. Marked here, in each use case that names this request, and in the status file.

## 1. What this is about

Taktus keeps what it must be able to do as requirements: one file per capability, each saying what
must be achieved, how that is checked, and what is explicitly not required. They are being moved
in four steps from the German project definition you wrote. This is the second step: the process
engine, governance and autonomy, and three cases of the virtual agent business — partner
interfaces, chains across departments, and the one person responsible for each department.

Seventeen requirements were written or moved. Where one only restates what your definition or the
vision already asks, the session wrote it without asking you, as you decided on 2026-10-01. Where
the definition gives a sequence and a few words of acceptance, a requirement needs a condition
precise enough that it cannot be met by interpretation, and writing it added substance. That
substance is new, and what a requirement says is yours to decide. This request lists it.

Six of the seventeen were never in the definition at all. Five were written by Taktus's own
repository in September, when the architecture decisions about wrong results and about exactness
were taken; the sixth, the decision request, was numbered later in conversation. None was put to
you as a requirement; they are now.

## 2. Why you are being asked

Entry M3.15 of `docs/decisions/anchors.taktus.md`: *"What a use case requires — what is new beyond
`docs/vision/` and the owner's project definition; bringing a use case up to them is M2.7: its
outcome, its verification condition and its boundary."* Every condition listed in section 4 is new
beyond both. Several are asked at once, so the question is asked once, as DEC-0030 did for the
first thirteen.

**Sources checked:** `docs/vision/` — principles 1, 6, 10, 11, 12 and 14 and the personas give the
direction of several conditions (each is named in section 4) but not the conditions themselves; the
ADRs — ADR-0004, ADR-0005, ADR-0008, ADR-0010, ADR-0014, ADR-0021 to ADR-0024 and ADR-0026 are the
source of many conditions, and an architecture decision says how something is built, not that a
use case must require it; both anchor pages — M3.15 makes what a requirement adds yours, M2.7 covers
only restoring; the register — DEC-0030, the same question for the first thirteen, was answered on
2026-10-08 with Option A, on the reason that each added condition came from an accepted ADR or made
a principle checkable and none moved a limit or an autonomy level. It decided the thirteen, not
these seventeen, and what a requirement adds stays yours under M3.15; the precedent is therefore
cited in the recommendation below, not applied in your place. DEC-0041 decides that
restoring is the session's, which is how the restorations here were made (NTC-0030); DEC-0055
accepted UC-6.10, which UC-4.2 draws on, and answers nothing here.

## 3. What you must decide

Whether the conditions the seventeen requirements of the second migration step add beyond version 2
of the definition stand.

## 4. What you need to know to decide

**What was added beyond version 2**, per use case. The source of each addition is named: an
architecture decision (ADR), the repository's own earlier text, a principle of the vision, or the
session.

| Use case | Serves | Added beyond version 2 |
|---|---|---|
| UC-4.2 every process seen as a diagram | P6, P7 | a run shows the diagram of the version it executes, not of the newest (session, reading "always in step") |
| UC-4.3 Taktus changes a process within the frame | P2, P10, P12 | a change is a new version and the old one stays; rollback is one act; the change passes the same registration, takeover instructions included, or becomes a proposal; five changes are always outside the frame — raising autonomy, changing a step's method, loosening exactness, touching an anchor, widening a worker's reach (ADR-0026, ADR-0004, ADR-0014, ADR-0008) |
| UC-4.4 Taktus proposes processes | P2, P9, P14 | accepting a proposal builds the process, and nothing runs before you commission it; a proposal drawn from a person's own work is shown to that person only (principle 14) |
| UC-4.6 self-healing within the frame | P8, P10, P12 | service-level objectives mean duration and share of completed runs; a retry is admitted against the budget (ADR-0005); an operation that cannot be safely repeated is never retried by Taktus (ADR-0024); where Taktus is unsure a fix lies within the frame it escalates instead; "repeated" means three times, configurable, never off (the repository's architecture text) |
| UC-4.11 error window and impact analysis | P6, P8, P12 | **all of it** — written by the repository with ADR-0021 on 2026-09-17; not in the definition |
| UC-4.12 remediation plan | P6, P10, P11, P12 | **all of it**, as UC-4.11 (ADR-0022). One change while moving it: a step a person carried out by hand is recorded in the incident with the **role** that did it, not the person, because UC-6.8 says an incident never names a person; the person stays in the activity log |
| UC-4.13 working out how a step becomes exact | P2, P8, P12 | **all of it** — written by the repository with ADR-0014 on 2026-09-21; the catalogue of five checks |
| UC-6.8 incident and incident report | P1, P6, P12, P14 | **all of it**, as UC-4.11 (ADR-0021, ADR-0023). The situation package for an escalated wrong result is a restoration of your definition, made without asking (NTC-0030) |
| UC-6.9 the exactness statement | P7, P8, P12 | **all of it**, as UC-4.13 |
| UC-7.1 the autonomy range | P10, P11, P12 | where several levels apply to one action, the lowest holds; the correction of a result that has left the system stays with a person at every level (ADR-0022); a raise without approval and quality history is refused and recorded, and the history counts wrong results as well as failures |
| UC-7.2 emergency stop | P10, P12 | the automatic trigger as a rule over five criteria, a set that cannot be emptied, scopes down to one run (ADR-0023, the repository's text of 2026-09-17); a stop by a person is your definition's |
| UC-7.3 rights, roles and least privilege | P11, P12, P14 | creating, approving and setting autonomy are three separate rights; a refused act is recorded with the right it lacked; the process's allowance is the ceiling of every worker's frame; rights are held only through roles, never granted to a named person outside one |
| UC-7.4 the decision request | P9, P10, P11, P14 | **all of it** — numbered after version 2; the shape, the halt at the boundary, the confirmation of a free-text answer, the register entry, visible waiting, a decider's response time private to them (ADR-0008, ADR-0015) |
| UC-8.5 cost control for every unit | P7, P8, P14 | a child budget never lets through what its parent refuses; at the budget the policy is chosen from halt-and-ask (default), wait for the next period, or a cheaper allowed model, and none crosses the line (ADR-0005); the budget says what it can promise; forecasts are a band; an anomaly is decided by a rule or a statistic, never a language model; what a named person consumed is visible only to that person — see below |
| UC-15.3 partner interfaces under a data contract | P4, P11, P12, P13 | a process without a data contract does not register; the contract is part of the process version; every import is checked before it is mapped and a deviating one is never corrected or guessed; every export is checked before it is sent; a proprietary format only where the partner offers nothing else, and said so |
| UC-15.4 end-to-end chains across domains | P5, P6, P8, P10 | a chain is a declared object; the record of a handover lists exactly what the next process read; a handover missing an item halts and escalates; **any** anchor — not only a legal one — stops the chain at that link's boundary; each link keeps its own control mode |
| UC-15.5 the responsibility anchor | P6, P10, P11 | a domain whose owner leaves is shown as without owner, and nothing in it is raised in autonomy meanwhile; no single domain may be left with no legal anchor (your definition says the catalogue as a whole); a domain is not shown as able to run without Taktus unless both its takeover and its removal test passed |

**Versions the roadmap does not name**, proposed by the session: UC-4.3 in `0.4.0`, where change
proposals arrive; UC-4.4 and UC-15.5 in `0.6.0`, with the skill lifecycle and the catalogue;
UC-15.3 and UC-15.4 in `0.7.0`, where a second domain exists. Every other version is the roadmap's.

**One place where your definition and the vision pull apart.** The definition lists a single person
as a unit that can carry a budget. Principle 14 forbids any figure that appraises a named person.
UC-8.5 keeps budgets for a person and shows what that person consumed to that person only; anyone
else sees it aggregated by role, team or department. A parent or a manager who sets a person's
budget therefore sees when it stops work, not how it was spent. If you want the budget's setter to
see a person's consumption, say so under Option B.

**Where the definition is superseded, nothing was asked.** Your definition's text is marked as
superseded, never deleted, in four use cases, each pointing at the decision that moved past it:
self-healing (UC-4.6) and escalation (UC-4.5) by the separation of failures from wrong results;
level 4 (UC-7.1) by the anchors that hold at every level; cost control (UC-8.5) by admission before
a step instead of a reaction after a budget is crossed, forecasts as a band, and the Takt beside
money. Those are your earlier decisions applied, not new ones.

None of the seventeen is built. Four are partly built and name the tests that prove the part:
UC-7.1 (a process without the reason for its autonomy does not register), UC-7.2 (a stop lands on a
step boundary), UC-7.3 (a worker gets only its credentials and its hosts), UC-8.5 (a run's budget).
Changing a requirement later is possible, but never in the change that implements it.

## 5. Options

### Option A — the added conditions stand (recommended)

- **Meaning:** the seventeen requirements, with what they add beyond version 2, are the standard
  the next changes are held to, including the person-only reading of UC-8.5 and the proposed
  versions.
- **Consequence:** the third step of the migration builds on them, and the `0.2.0` work — retries,
  rights, decision requests, budgets — is held to them.
- **Effort:** none now.
- **Reversibility:** cheap until a use case is built; after that, a change is a request per use case,
  which is the intended cost.
- **Why recommended:** each added condition either comes from an architecture decision you already
  accepted, from the repository's own text that the decisions rest on, or makes a principle
  checkable that was only asserted; none moves a limit or an autonomy level, and where two readings
  were possible the stricter was taken. It is the reason you accepted for the first thirteen
  (DEC-0030).

### Option B — they stand, except the ones you name

- **Meaning:** you name use cases and the condition you want changed, removed or read otherwise in
  each — for example the person's consumption in UC-8.5, or a version; a session changes them in a
  change of their own.
- **Consequence:** those use cases wait until the change is merged; the others are in force.
- **Effort:** an hour of your reading, a session's afternoon.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing: the provisional answer is in force. If no answer arrives by 2026-10-22, the `0.2.0` work
that builds UC-4.6, UC-7.3, UC-7.4 and UC-8.5 starts on Option A, and changing an added condition
afterwards costs a request per use case instead of one edit now.

## 7. How to answer

"DEC-0069: Option A." — or "DEC-0069: Option B" followed by each use case and the change you want in
it — in issue [#111](https://github.com/Jersyfi/taktus/issues/111). A free-text answer is read back as
an interpretation and confirmed before it is acted on.
