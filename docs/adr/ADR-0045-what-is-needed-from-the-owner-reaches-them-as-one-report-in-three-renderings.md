# ADR-0045 — What is needed from the owner reaches them as one report in three renderings

**Status:** accepted · builds UC-6.11 (issue #85) on ADR-0008, ADR-0028, ADR-0029 and ADR-0042

## Context
Something Taktus needs from the owner of a project — a decision, something only the owner can
provide, a date — had one place in the product: a decision request on the control plane's own
surface (ADR-0042). The owner had to go there to see it. A need, a date, or a failure Taktus
noticed about itself (DEC-0058) had no place at all.

UC-6.11 §2 asks for more (provisional under DEC-0087). One event has three renderings: a text for
a repository, a message in the channel the owner chose, and a view with its history. All three
carry the same identifier, the same needed items and the same date. The message is in the owner's
language. A report states what is needed, the steps, what stands still and the date; one without
any of the four is not sent. The owner answers in the channel. The answer is filed only after its
reading was reflected back and confirmed, and only from the owner or someone the owner named.
Where a ticket system is configured, the report goes there too, and closing it files nothing. A
message that cannot be delivered leaves the event in place and shows the failure. No message
carries a secret.

Five questions had to be answered. What is the event, given that the ledger holds no text
(ADR-0006)? Where does the owner's language live, given that the core names no language? How
does an answer in a chat find the report it answers? How is it read? And which component owns it?

## Decision

### 1. The event is a report, kept by `reporting`
A **report** is the record of one thing needed from the owner. It has a kind — `decision`,
`need`, `date` or `failure` — and the identifier of the event: a decision request's own, or the
need's, the date's, the failure's. It holds four items: what is needed, the steps to provide it,
the work that stands still, and the date. It holds the answers it offers, the links it concerns,
every delivery with its outcome, and its history.

The report is the record the ledger entry points to. `report.raised` carries the new reference
`refs.report_id` (`contracts/shared/v1/LedgerEntry.json`, added optional) and the digest of the
repository text. `report.delivered`, `report.answered`, `report.filed` and `report.task_closed`
follow, each content-free.

The `reporting` component owns it (ADR-0029: reports and their delivery are the reader's side).
Its package arrives with this use case: `src/taktus/components/reporting/`, with its
independence contract and its line in `tests/architecture`. It owns no figure.

A report without one of its four items is refused with `NotSent`, and nothing is stored or sent.
So is one whose renderings would carry a secret value the instance holds.

### 2. Three renderings, composed from the report alone
`domain/service/rendering.py` composes each rendering from the report and from nothing else:

- the **repository text** — English, as everything in a repository is (CLAUDE.md §9, DEC-0015);
  minimal; it names where an answer was given — the channel, the address, the thread — and never
  what was said there;
- the **message** — in the owner's language, with every link the report concerns, the task in
  the ticket system and, where the control plane's address is configured, the report's view;
- the **view** — the report with its deliveries and its history, served at
  `GET /owner/reports` and `GET /owner/reports/{id}`; the repository text is served at
  `GET /owner/reports/{id}/text`.

The view names nobody. A history entry says whether the reader acted, not who did: a view that
named the answerer would show how long that person took to everyone who reads it (ADR-0015).

### 3. The channel is configuration, and so is the language
An **owner-facing channel** is one tenant's configuration (`taktusctl owner-channel set`). It
names the owner's identity and the identities the owner named. It names the roles whose decision
requests go to the owner (`owner` by default), the channel and the address a report is said at,
optionally a ticket system as a connector capability and operation, and optionally the address
the control plane is reached at.

It names the owner's language as a **phrasebook**: every sentence the owner reads, and the words
an answer is read by. A tenant writes its own, or names a language and takes the one Taktus
ships. The shipped phrasebooks are files beside the composition root
(`src/taktus/composition/phrasebooks/`), German and English today. No sentence of a phrasebook
is in a component; a test holds that.

### 4. A report is said through the channel's reply operation
A report is said through the operation `<channel>.reply` of the connector that serves the
configured channel (`contracts/connector/v1` §7), as Taktus itself (ADR-0033), at the configured
address and without a thread. The contract now says that the operation's output names the
`thread` the message opened. The report keeps that thread. A task is opened through the
configured operation with a title and the repository text as its body, and the message links it.
Every delivery has an idempotency key derived from the report, so a repeat after a restart lands
once.

A delivery that fails is kept with its reason (`no_connector`, `refused`, `unreachable`). A
delivery withheld because it would carry a secret is kept as `withheld`. Either way the report
stays: in the view, in its history and in its repository text. `DeliverReport` tries again what
was not delivered.

A decision request raised by the run reaches the owner the moment it is raised. The composition
root binds the run's decision port to the channel (`RequestsOfTheRun.report_to`). A request for
a role the channel does not carry stays where ADR-0042 put it.

### 5. An answer in the report's thread is taken, read, reflected and confirmed
The intake gains a port, `ChannelAnswers`. A message written in the thread of a delivered report
is handed to the reporting component, from the identity its sender was placed as, or from
nobody. It is not kept as an intake event and does not become a command. Every such message is
answered in the thread, once:

1. **Only the owner, or someone the owner named, is filed** (UC-1.7). Anyone else is told that
   the answer is not filed, and nothing changes. That includes a sender nobody could place, who
   is not offered a link there.
2. **An answer is read by a rule.** A decision request's answer is read by the decision
   component's own rule (ADR-0042 §4) and kept there. A need's, a date's or a failure's single
   offered answer — that it is done — is read when the whole message is one of the phrasebook's
   `done_words`. An answer that reads as none of the offered answers is asked back.
3. **Only a confirmed reading is filed.** The reading is sent back without quoting the answer.
   The same person confirms it with one of the phrasebook's `yes_words` or rejects it with one of
   its `no_words`. A decision is filed as its register entry, which then hands the run on; any
   other answer is filed on the report itself. Anything else written while a reading waits is a
   new answer.

Closing the task in the ticket system files nothing (`CloseTask`): the report's history records
it, and the report stays open.

### 6. A failure Taktus noticed goes the same way
`OwnerChannelWiring.failure` raises a report of kind `failure` through the same handler, channel
and checks. It is the entry the run's noticing will call (issue #100).

## Alternatives
- **The three renderings from the ledger.** The owner's text said so. The ledger holds no text
  (ADR-0006), so the renderings would have nothing to show; UC-6.11 §4 already records this.
- **Phrasebooks inside the reporting component.** It would be shorter, but every sentence would
  then be in the core, and a tenant could not add a language without a release.
- **Answers read by a model.** It could read more intent, and it would have to be confirmed all
  the same (ADR-0042). A rule fails visibly in the reflection.
- **A post operation configured by name, `chat.threads.post`.** The core would then name a
  capability of one connector. The reply operation is the channel's own, declared by contract.
- **The answer stored as written.** The repository text would then carry the conversation, which
  CLAUDE.md §9 forbids. The decision component keeps the raw answer of a decision, as it did.

## Consequences
- `reporting`: `Report`, `OwnerChannel`, `Phrasebook`; the handlers that configure, raise,
  deliver, answer and close; the queries and the view; the ports `Deliveries`, `DecisionAnswers`,
  `SecretValues` and `Phrasebooks`.
- `ports/connector.py`: `ChannelAnswers` and `Taken`. `ReceiveIntakeHandler` takes an optional
  `answers` and returns `answer` on its outcome.
- `contracts/shared/v1/LedgerEntry.json`: `refs.report_id`. `contracts/connector/v1` §7: the reply
  operation says reports too, and its output names `thread`.
- Ledger kinds `owner_channel.configured`, `report.raised`, `report.delivered`,
  `report.answered`, `report.filed` and `report.task_closed`.
- Migration 0020: the tables `owner_channel` and `report`.
- HTTP: `GET /owner/reports`, `GET /owner/reports/{id}`, `GET /owner/reports/{id}/text`; the
  intake answers `answer` for a message in a report's thread. Command line:
  `taktusctl owner-channel set|show`.

## Where this promise ends
The renderings agree because they are composed from one record; the repository text is served
and handed to a ticket system, not committed into a repository. Nothing yet raises a need or a
date report in a run: the handler exists, and a decision request and a failure are wired to it;
the steps of a process that raise the others arrive with the processes that need them. The
failure path is an entry point; noticing the failure is #100.

A report is matched to an answer by the thread the reply operation names; a connector whose output
names none receives reports and matches no answer. The match reads every report of the tenant.
A failed delivery is tried again only when `DeliverReport` is called; nothing calls it on a
schedule yet. Closing a task is recorded only when something calls `CloseTask`; the repository
connector does not yet report a closed issue as an event.

The phrasebook's words are matched as whole messages: a person who writes "ja, passt" is asked
back. The decision's own rule reads the option letter and inherits ADR-0042's limits. A secret is
recognised only as one of the values the instance holds, eight characters or longer: a value the
instance does not hold, or a part of one, is not seen. Only German and English phrasebooks ship.
Whom the owner named is configuration an operator writes; the configuration does not prove that
the owner chose them. A decision confirmed on the control plane's surface is not reflected on the
report, which keeps waiting until an answer in the thread is told that it was taken already. The
owner's questions in the channel (UC-6.4, UC-1.5) and the web app's page (#105) are not built.
Against the real chat service nothing has run: that waits for NEED-0018.
