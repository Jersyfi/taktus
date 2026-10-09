# NTC-0095 — What is needed from the owner reaches their chat

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-09
**Raised in:** [#PRNUMBER](https://github.com/Jersyfi/taktus/pull/PRNUMBER), for issue #85

## 1. What was decided

Until now a decision request waited on the control plane's own surface, where the owner had to go
to find it, and a need, a date or a failure Taktus noticed about itself reached the owner nowhere
in the product. Now each becomes a report to the owner (ADR-0045):

- A tenant configures its **owner-facing channel**: the owner's identity, the people the owner
  named, the channel and the address reports go to, a ticket system if any, and the owner's
  language as a phrasebook (`taktusctl owner-channel set`). Taktus ships German and English.
- A **report** names what is needed, the steps, the work that stands still and the date. One
  without any of the four, or one that would carry a secret value the instance holds, is not
  sent and not stored.
- A report is said in the owner's conversation through the channel connector's reply operation,
  opened as a task where a ticket system is configured, and kept with every delivery and its
  outcome. A delivery that fails leaves the report in its view and in its repository text, the
  failure shown in both.
- A decision request addressed to a role the channel carries, `owner` by default, reaches the
  owner the moment the run raises it. A failure Taktus notices about itself goes the same way
  (DEC-0058).
- What the owner writes in a report's thread is taken from the intake and is no command. It is
  read by a rule, its reading sent back, and filed only once the same person confirmed it — a
  decision in the register, which then hands its run on. An answer from anyone but the owner or
  someone named is told that it is not filed.
- The control plane serves the view (`GET /owner/reports`, `GET /owner/reports/{id}`) and the
  repository text (`GET /owner/reports/{id}/text`).
- The ledger reference `refs.report_id` is added, optional, to `LedgerEntry.json`; the connector
  contract's reply operation now also says a report and names the `thread` it opened.

## 2. The evidence

- Issue #85 and UC-6.11 §2, in force provisionally under DEC-0087: every condition of §2 but the
  owner's questions, which the issue places with UC-6.4 and UC-1.5.
- `tests/components/reporting/test_owner_channel.py` holds each condition over the components,
  and `tests/adapters/connectors/test_owner_channel_chat.py` holds the path against the chat
  connector and the fake of its service, with the repository connector as the ticket system.
- The contract changes add and break nothing: `refs.report_id` is optional, so every entry written
  before is unchanged and its hash recomputes; the reply operation's input is unchanged.

## 3. What was considered

- **The chat rendering only, no report of its own.** Rejected: a need, a date and a failure have
  no record in the product to render from, and the ledger holds no text (ADR-0006).
- **Posting through `chat.threads.post`, configured by name.** Rejected: the core would name a
  capability of one connector; the reply operation is the channel's own, declared by contract.
- **Delivering on the next scheduler tick instead of when raised.** Rejected for now: the owner
  learns of a decision request the moment the run halts on it. Retrying a failed delivery on a
  schedule is left open in ADR-0045.

## 4. Which entry permits it

M2.4: "A change of what the software does, made inside an agreed scope, that breaks no contract,
moves no limit or autonomy level and says nothing public." The scope is issue #85 and UC-6.11 in
the roadmap's `0.2.0`; both contract changes are additive; no limit or level moves; the messages
go to the tenant's own owner, not to the public. No entry of mode 3 or 4 names it.
