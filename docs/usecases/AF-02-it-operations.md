# UC-02 — Systems operation, unattended

Blueprint `it-operations`. An orchestrator that runs a platform: reports, documents, updates,
monitors, heals within its frame, and fetches a person exactly where that is required.

Planned for `0.7.0`. It needs a much broader connector base than UC-01 — cluster, metrics,
virtualisation, object storage. **Depth in one case first, breadth second.**

---

## 1. Origin and boundary

This use case is derived from a single, fully written operating mandate for one specific platform.
That mandate is **a requirements source for this case and for nothing else.** It is not implemented
here, and no general Taktus rules are drawn from it. An earlier draft did exactly that; it was a
mistake and has been withdrawn.

One finding from it is product-relevant and stands.

**Autonomy belongs to the action, not only to the process.** A real operating mandate distinguishes,
inside *one* process:

| Action | Autonomy |
|---|---|
| roll back to the last healthy version | automatic |
| restore from a backup | never automatic — alert, diagnosis, prepared command, human decision |
| restart a stateless helper system | automatic, escalating |
| restart the main system | never |
| patch and minor update | automatic |
| major update | waits for approval |

Four autonomy levels per process cannot express that. The action level is therefore part of the
model.

---

## 2. Translation

| In an operating mandate | In Taktus |
|---|---|
| maintain your own operating doctrine | handover documentation maintained automatically |
| a fixed split of work between server, CI and AI | method kinds: `rule` versus `llm`/`worker` |
| one log entry per change: what, why, how to undo | the ledger |
| a monthly report: what changed, what alerted, what it cost | a periodic report |
| never delete a volume, database or backup without asking | a legal anchor |
| a credentials register listing names, never values | the secret store reference |
| every alert links to a runbook | escalation with a situation package |
| rollback as the only automatic remediation | self-healing within the frame |

---

## 3. Processes

| ID | Process | Autonomy |
|---|---|---|
| O-01 | Update stream: review proposals, roll out patch and minor, present majors for approval | 4 / anchor for majors |
| O-02 | Deployment watch with rollback on a failed rollout | 4 |
| O-03 | Backup watch and a monthly restore drill | 4 for the drill, anchor for a real restore |
| O-04 | Alert handling: assess, fix within the frame, otherwise a situation package | 3 |
| O-05 | Documentation upkeep: architecture, runbooks, credentials register, operations log | 4 |
| O-06 | Monthly report: changes, alerts, cost, drill result, what needs a person | 4 |
| O-07 | Capacity and cost: utilisation, forecast, recommendation | 3 |

---

## 4. Dependencies

Autonomy per action class (`0.7.0`) · connectors for cluster, metrics and object storage · legal
anchors (`0.2.0`) · value ledger for the cost part (`0.5.0`).
