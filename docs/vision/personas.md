# Actors

Who deals with Taktus, and what each one sees. The views follow from these roles; the roles do
not follow from the views.

| Actor | Role in the system |
|---|---|
| **Operator** | Gives commands through any channel, shapes plans in dialogue, commissions the work |
| **Process owner** | Defines processes, autonomy levels, governance and the organisational structure |
| **Employee** | Works alongside Taktus, sees operational reports, takes over where needed |
| **Management** | Sees cost, predictability, quality, utilisation, risk |
| **Executive** | Sees the strategic contribution, the progress of the transformation, opportunities and dependencies |
| **Investor** | Sees the demonstrable value of the deployment |
| **Administrator** | Runs, configures and manages the platform |
| **Individual or family** | Uses Taktus for personal automation, shares models within a group |
| **Taktus itself** | Plans, delegates, configures tools, executes, watches, reports |
| **Models** | Interchangeable inference, through the model contract |
| **Workers** | Interchangeable execution behind the worker contract — coding agents, agent runtimes, script runners, training jobs. **They execute; they do not decide** |
| **External tools** | Repositories, ticket systems, knowledge systems, communication tools, any documented API |

---

## Two roles that carry an obligation

**The responsibility anchor.** Every instantiated domain has exactly one human owner. They see
the domain in their view, receive its escalations, decide its autonomy raises, and are the
addressee of its takeover test. Full autonomy without responsibility would be a bus factor of
zero in another form.

**The decider.** Whoever answers a decision request. Their response time is measured because
throughput depends on it — and that measurement belongs to them and is visible only to them
by default (principle 14, ADR-0015).

---

## What a persona is not

A persona is not a permission set. Permissions follow the organisational structure and the
role model; a persona describes what someone is trying to achieve. Two people with the same
permissions may be different personas, and the views must serve both.
