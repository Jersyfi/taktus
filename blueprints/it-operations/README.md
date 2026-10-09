# Blueprint `it-operations`

The blueprint of use case UC-02 (`docs/usecases/AF-02-it-operations.md`): systems operation,
unattended — an orchestrator that runs a platform, reports, documents, updates, monitors, heals within
its frame, and fetches a person exactly where that is required. The roadmap places it in `0.7.0`. No
process of it exists as a bundle yet; its processes and their autonomy per action are described in
UC-02.

This blueprint also carries the reference assistant of the IT domain, the IT service chat.

---

## The IT service chat — UC-12.2

An assistant for the people an IT department serves, rolled out into the organisation's communication
tool (UC-12.1). It is the reference for the pattern every assistant follows — a channel, an agent,
knowledge, tools, a process and governance (UC-12.3).

**What it does.** The chat answers questions, presents solutions and finds the documentation that fits
(UC-5.5). Where the person cannot help themselves, it fills in the form of the organisation's ticket
system and submits it (UC-5.3), with everything it has already learned in the conversation, so that
nobody is asked twice.

**What must hold.**

- The quality of its answers is measurable: requests resolved without a ticket against requests that
  became one, per period.
- It knows its limits. What it cannot resolve it escalates to a person, with the conversation and what it
  found as the situation package (UC-4.5).
- Every answer names its source (UC-5.5).
- It is a normal Taktus process with an agent: the same governance, the same reporting and the same value
  balance as any other (UC-12.1). Its channel is a rollout channel: it acts with the agent's rights plus
  the credentials of the person using it, and a message to it is never a command to Taktus (UC-12.1).
- A request becomes at most one ticket, however often a step is repeated (ADR-0024).

**Where it rests.** The definition numbers the escalation `UC-4.6`; this repository numbers it `UC-4.5`
(`docs/usecases/NUMBERING.md`). Definition `UC-12.2`. The roadmap names no version for it; it belongs to
this blueprint's `0.7.0`. What this description adds beyond the definition is asked in DEC-0087.
