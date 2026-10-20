# ADR-0111 — Connectors over open standards: mail, metrics and a check

**Status:** accepted · amends ADR-0024 (a scenario without a write) · serves UC-03 §8,
DEC-0201 · issue #441

## Context

The second tenant hosts Taktus itself (DEC-0201). Its systems are not named yet (NEED-0028).
Some of the capabilities UC-03 §8 asks for are served by open standards whatever the product:
mail by IMAP and SMTP, metrics by the Prometheus HTTP query API, a check by HTTP. A connector
for each can be built now.

Five facts shape the decision.

- A connector is an MCP server, and every operation declares its effect and, when the effect
  leaves the system, how a repeat is recognised (ADR-0024).
- Intake is a function from a signed delivery to a command. The transport that received the
  delivery is not part of it. The daemon hands every delivery on `POST /intake/{channel}` to
  the connector that serves the channel (ADR-0024 §5).
- A delivery whose event identifier the tenant already holds is a redelivery. The `command`
  component keeps nothing for it (ADR-0048 §4).
- The conformance suite's scenario required at least one write. A connector that only reads
  could not pass it.
- Processes reference capabilities, never products. A product name in the core is a finding
  (CLAUDE.md §6).

## Decision

### 1. Three connectors, each in a directory of its own

| Connector | Directory | Capability | Operations |
|---|---|---|---|
| mail | `connectors/mail/` | `mail.messages`, `channel.mail` | `mail.messages.read` (read), `mail.messages.send` (delivery, marked), `channel.mail.reply` (delivery, marked) |
| metrics | `connectors/prometheus/` | `metrics.series` | `metrics.series.query`, `metrics.series.range` (both read) |
| check | `connectors/httpcheck/` | `check.http` | `check.http.run` (read) |

The query API carries a product's name. That name appears only in the metrics connector's
directory, its README and configuration. `prometheus` joins the product names the architecture
test refuses in the core and in the contracts.

The three share one module, `connectors/serving.py`: the MCP server around their operations,
the reading of a credential from its file, and the faults the suite is proven against. It
serves only these three. The existing connectors keep their own servers.

### 2. A message sent is marked by its message identifier

`mail.messages.send` derives the message identifier from the idempotency key: the first 40
hexadecimal digits of the key's SHA-256, `.taktus@` and the sender's domain. The key itself
never leaves Taktus. Before it sends, the connector searches the sent folder over IMAP for that
identifier. A copy found is the original, returned with `replayed: true`. After the SMTP server
accepted the message, the connector files a copy there, or the server does so itself
(`--server-files-sent`).

### 3. Mail reaches the intake through a relay

A mailbox sends nothing; it is read. The relay is a second process of the mail connector. It
reads the inbox over IMAP and delivers each new message to the instance's intake address of
`channel.mail`. The delivery is a JSON body with the mailbox, the UID and the message in base64.
It is signed under `hmac-sha256` with the intake secret. The instance hands it to the
connector's intake tool like any webhook delivery. Nothing in the core changes.

The relay sets the keyword `$TaktusRelayed` on each message the instance answered. It keeps no
memory of its own. The mailbox does.

### 4. Intake is de-duplicated by message identifier

The event identifier is the message's `Message-ID`. A message without one is identified by the
digest of its bytes. The same message relayed twice, or found twice in the mailbox, is one
event: the second is a redelivery (ADR-0048 §4).

The sender is the digest of the address the message came from, `sha256:` and 64 hexadecimal
digits. The contract asks for an opaque account, never an address. The reply address is the
address the message asks replies to go to, because that is where a reply must land. The
connector refuses a message it sent itself as `own_action`. It refuses an automatic message
(RFC 3834) as `unsupported_event`, so that two automata never answer each other.
`channel.mail.reply` marks its own message `Auto-Submitted: auto-replied`.

### 5. A check reports its outcome, not an error

`check.http.run` sends one GET or HEAD to a path under the service the connector is configured
for. A call cannot name another host. The expectation names the status, a text the body
contains and the longest duration. The result is `passed` or `failed`, with each failed part,
the status and the duration in milliseconds. A service that does not answer is a failed check:
observing that is what a check is for. Only a call the connector cannot make is an error,
`invalid`.

The contract has no connector without the requesting identity's credential (C-03). The check
sends it as a bearer token to the configured service and nowhere else. A service that admits
anyone ignores it.

### 6. A scenario may name no write

The schema of the scenario no longer requires a write. A scenario without one passes C-05 as
not applicable when the declaration has no operation that leaves the system and can be
repeated. Where the declaration has one, C-05 is inconclusive: a pass would prove nothing.

### 7. What of OpenTelemetry and signed webhooks waits

OpenTelemetry is a way for a service to send its metrics, traces and logs to a collector. It
offers no way to read a series back. Reading needs the store the collector writes to, and a
store that receives OpenTelemetry metrics and answers the query API is read by the metrics
connector. A receiver of OpenTelemetry data is therefore not needed now. It is needed only for
a system that pushes and keeps nothing to read.

The issue names signed webhooks among the open standards, and its verification does not. The
intake already verifies `hmac-sha256` and `hmac-sha256-timestamped`. A connector for the open
specification of signed webhooks, whose signature also covers the delivery's identifier and
its moment, needs a third scheme in the contract. It is issue #532.

## Alternatives

- **An operation that fetches new mail, called by a process.** A process would have to keep a
  cursor and run on a schedule, and every message would become a step's result, not a command.
  Intake is how the outside starts work.
- **The daemon reads the mailbox itself.** The core would speak IMAP, which the adapter
  obligation forbids.
- **The idempotency key in a header of the message.** It would show a run's identifier to every
  recipient. Its digest in the message identifier is enough to find the copy.
- **A failed check as `unavailable`.** The run would retry or escalate a check whose finding is
  that the service is down. That finding is the result.
- **A dummy write for the read-only connectors.** It would make the suite pass by an operation
  nobody needs.

## Consequences

- `src/taktus/adapters/driven/connectors/mail/`, `prometheus/`, `httpcheck/` and
  `serving.py`; the fakes `tests/fakes/mail_service.py` and `tests/fakes/metrics_service.py`.
- `contracts/connector/v1`: `Scenario.writes` without `minItems`; the fixture
  `scenario/valid/read-only.json` replaces `scenario/invalid/no-write.json`. The suite passes
  C-05 as not applicable, or as inconclusive, as §6 says.
- `CREDENTIALS.md`: `MAIL_PASSWORD`, `MAIL_INTAKE_SECRET`, `METRICS_TOKEN`, `CHECK_TOKEN`.
- Each is added to an instance by one entry of `TAKTUS_CONNECTORS`. S-01 tests each like any
  connector. No process uses one yet, so each is `untested` and its maturity `experimental`.

## Amendment — `serving.py` serves the vendor connector too (2026-10-20)

§1 said `serving.py` serves only the three connectors. The vendor connector of ADR-0117 puts a
vendor's MCP server behind the contract, and it serves the contract the way these three do: a
declaration, one tool per operation, a credential read from its file at the call, the faults
the suite is proven against. It is served by the same module rather than by a copy of it. The
existing hand-written connectors still keep their own servers. Nothing changes for the three.

## Where this promise ends

A message sent is recognised as a repeat only by its copy in the sent folder. Between the SMTP
server's acceptance and the copy filed lies one IMAP session. A connector stopped exactly there
has sent a message no lookup finds, and a repeat sends it again with the same identifier. A
server that files sent messages itself, and is said to with `--server-files-sent`, closes that
gap only as far as it files every message. A server that rewrites the message identifier
breaks the mark, and every repeat is sent again.

Intake is de-duplicated by `Message-ID` as the sender wrote it. Two messages a sender gave the
same identifier are one event. Two copies of one message that arrived with different
identifiers are two. The relay delivers at least once. Messages arrive at the intake no sooner
than one interval after they arrived in the mailbox, and at most 50 in one pass. A relay whose
secret is not the connector's keeps every message and says so in its log; it does not stop.
The digest of an address is the same for every tenant: it hides the address from a reader of
the ledger, not from someone who guesses it.

A check measures one request from the connector's host, from sending to the end of a body of at
most one MiB. It says nothing of the service seen from elsewhere. A redirect is a status, not
followed. The duration includes the connection and the TLS handshake.

The metrics connector reports at most `limit` series, at most 10 000, and says when it cut.
A value is a number only where the store gave a finite one. The connectors are proven against
fakes of their servers in every run of the gates. A real mail server, metrics store or service
has not been reached by them yet; the business's own are, once NEED-0028 names them.
