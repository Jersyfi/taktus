# ADR-0118 — A finding is classified by the release's list, and leaves signed to the project's intake

**Status:** accepted · amends ADR-0112 §1 and §6: the level is part of the setting, and an instance outside the project submits to the intake of the project's own instance · extends ADR-0046 and ADR-0106 · issue #555, UC-6.12, DEC-0214, DEC-0217

## Context

ADR-0046 made a finding of every block whose cause was a lack of an adapter. ADR-0112 let an
instance outside the project send its findings, by pseudonym, through a connector its operator
names. Two things were wrong with that for a customer's instance (DEC-0217).

- **Not every lack is the product's.** An instance that did not configure an adapter the
  product ships raised a finding all the same (ADR-0046, "Where this promise ends"). So did a
  lack in an adapter, a process or a bundle the customer brought. Neither is something the
  product can fix. The owner decided that such findings never reach the project.
- **A second app.** ADR-0112 §6 needed an identity on the repository service for every sending
  instance. Asked of the owner, it would have been a second app of his. The owner rejected that:
  Taktus is one app on the repository service (DEC-0214).

The owner approved the following in DEC-0217. A release carries a list of what it ships. A rule
classifies every lack against it. A local lack stays on the instance and reaches the customer's
own owner. The operator chooses how a product candidate leaves: `off`, `review` or
`automatic`. What leaves is signed, and the project's own instance opens the issue.

## Decision

### 1. The release carries the list of what it ships
`src/taktus/composition/shipped.json` lists every worker and every connector the release
ships. Each entry names the adapter, the capabilities it offers and, for a connector, its
operations. The file sits inside the package, so an instance reads the list of the release it
runs (`composition/shipped.py`, `load`).

`make generate` writes the file (`build`). The connectors' entries come from each connector's
own declaration under `adapters/driven/connectors`. The workers' come from each worker's
`CAPABILITIES` under `workers/`, read from its source without importing it.
`tests/composition/test_shipped.py` fails when the file is not what `build` makes. The list
therefore cannot drift from what ships.

Two packages are left out. The vendor connector offers whatever a vendor's server offers,
under a manifest its operator writes (ADR-0117). It ships no capability of its own. The MCP
client is the port's adapter, not a connector.

### 2. A rule classifies every lack
`classify` (`reporting/domain/service/findings.py`) reads a lack — its cause and what was
lacking — and the list. Nothing else decides. It is a rule, never a probabilistic method.

| Kind | When |
|---|---|
| **local: configuration** | a shipped adapter offers what was lacking: a worker with every capability, a connector with the capability, a connector with the operation |
| **local: own development** | what was lacking lies outside the product's vocabulary, or an operation's capability is served by no shipped connector |
| **product candidate** | everything else |

The *product's vocabulary* is the set of first segments of every capability and operation
shipped: `repository`, `code`, `knowledge` and so on. A capability outside it was named by the
project: by its own adapter, its own process or its own bundle. An operation whose capability
no shipped connector serves was met on a connector the release does not ship. The lack lies in
that connector, which is the project's own.

A configuration lack names the shipped adapters that would serve it. A report a person writes
by hand is always a product candidate, its target chosen by its writer.

### 3. A local lack never leaves, and reaches the customer's owner
A local lack is never sent, neither by the scheduler nor on a person's yes. It is one more
alert of ADR-0106 (`kind: local_lack`). It is in effect while a step still waits for the lack,
and clears when every step that waited could start. Its report, of kind `failure`, reaches the
tenant's own owner-facing channel. For a configuration lack it names the shipped adapters and
the setting that configures them. For a lack of own development it says to give the project's
adapter what the step needs, or to report the lack by hand if the product should offer it.

### 4. The operator's level
`TAKTUS_FINDINGS_LEVEL` says how a product candidate leaves.

- **`off`**, the default. Nothing is sent. The candidate is recorded and shown
  (`taktusctl findings`), and the operator may send its text by hand.
- **`review`**. The scheduler sends nothing. `taktusctl findings review` shows each candidate
  that holds something not yet sent, exactly as it would leave. The person answers `send`,
  `not` or `local`. `send` sends it now. `not` sends nothing and offers it again at the next
  review. `local` records `finding.local` in the tenant's ledger, with the digest of the lack's
  key, and the lack is never offered again.
- **`automatic`**. The scheduler sends every candidate the rule raised, as ADR-0046 did. A
  report by hand is never sent by the scheduler at any level. `taktusctl findings report` shows
  it and sends it only on the person's yes (ADR-0112 §5).

The level is part of the operator's setting. `finding.enabled` records it as its outcome,
beside the digest of the address (amends ADR-0112 §1). A change of the level alone is recorded
too.

### 5. Signed to the intake of the project's own instance
An instance has two ways out. Through its own connector to the repository, as ADR-0046 built
it: `TAKTUS_FINDINGS_CONNECTOR`. Or to the intake of another instance:
`TAKTUS_FINDINGS_INTAKE`, an HTTP address. The two exclude each other. An instance outside the
project uses the second. It needs no account and no app of its own on the repository service
(amends ADR-0112 §6).

To an intake, each occurrence goes as one *submission*: closed values only — the lack, the
occurrence by pseudonym, the sender. A report by hand goes as its title and its checked body.
The sender signs the submission's bytes with Ed25519. The seed of its private key is derived
from the tenant's pseudonym key of ADR-0112 §3, by an HMAC under a purpose of its own. Nothing
new is kept. The key is as safe as the pseudonym key, and drawn once with it. What the intake
took is recorded on the sender as `finding.submitted`, with the digest of the submission's
bytes, so it is never submitted twice.

### 6. The intake
`POST /findings/intake` on the API (`adapters/driving/rest/findings.py`) takes one signed
submission. It admits no credential: the signature is the only proof. An operator opens it by
naming the tenant whose owner confirms senders, `TAKTUS_FINDINGS_INTAKE_TENANT`. It writes
through the instance's own connector, so `TAKTUS_FINDINGS_CONNECTOR` is set too. Elsewhere the
route answers 404. The use case is `FindingsIntake` (`reporting/application/service/
finding_intake.py`). It does five things, in this order.

1. It verifies the signature, before it reads the payload. A forged one is answered `forged`
   (401), and nothing is recorded.
2. It reads the submission. One that is none, or carries the shape of a personal datum by the
   rule of ADR-0112 §4, is answered `invalid` (422).
3. It holds a new sender. The first submission under a public key records `intake.sender` with
   the key and the sender's identifier. It raises a report of kind `need` in the owner's
   channel, asking the owner to confirm the sender. Until the owner answers it that it is done,
   with the reading reflected back and confirmed (ADR-0008), every submission is `held` (202).
   A key that names a sender another key registered is `refused` (403). At most five new
   senders wait at once; a further one is `limited` (429).
4. It limits each confirmed sender to `TAKTUS_FINDINGS_INTAKE_RATE` submissions an hour, 30 by
   default, counted from its `intake.received` entries. One over is `limited` (429).
5. It opens or adds to the issue with the instance's own channel, as the instance sends its own
   findings (`deliver`). The texts are the intake's sentences around closed values, in the
   form its own operator configured. The same lack from another sender adds an occurrence. An
   occurrence the repository holds already is `known` (200). A report opens an issue of its
   own (201).

Every submission taken is recorded as `intake.received`, the sender as its actor.

## Alternatives
- **A second app for every sending instance, as ADR-0112 §6 asked.** Rejected by the owner:
  Taktus is one app on the repository service (DEC-0214).
- **The intake as an issue form anyone may fill.** Rejected: an issue opened under a customer's
  account says in public who sent it, possibly a person (principle 14).
- **Classify by the instance's configured adapters.** Rejected: whether a configured connector
  is the product's or the project's cannot be read from its declaration with certainty. The
  list and the vocabulary are known without asking anything outside.
- **A shared secret between sender and intake.** Rejected: the owner would have to hand it to
  each customer through a channel both trust. A public key needs no secret channel; the owner
  confirms what arrives instead.
- **A table for senders, by migration.** Rejected for now: the ledger and the object store hold
  the key and the first contact, as they hold the pseudonym key (ADR-0112 §3). The owner's
  confirmation is the report's own state.
- **Composing the issue's text on the sender.** Rejected: a confirmed sender could then write any
  words into the project's repository. The intake composes them from closed values.

## Consequences
- `Shipped`, `ShippedAdapter`, `Classified`, `Submission` and `FindingsLevel` in
  `reporting/domain/model/finding.py`; `classify` in `domain/service/findings.py`.
- The ports `FindingIntake`, `Signatures` and `Signed`; the adapter
  `adapters/driven/signing`.
- `ProductFindings` takes `shipped`. `Sending` takes `level` and `signatures`, and its channel is
  a channel or an intake. New: `classified`, `pending`, `send_one`, `call_local`,
  `called_local`, and `deliver` as a function the intake shares.
- The use case `FindingsIntake`, and its route.
- The alert kind `local_lack`; `Alerts` takes the product findings.
- The ledger gains `finding.submitted`, `finding.local`, `intake.sender` and
  `intake.received`. No migration.
- The settings `TAKTUS_FINDINGS_LEVEL`, `TAKTUS_FINDINGS_INTAKE`,
  `TAKTUS_FINDINGS_INTAKE_TENANT` and `TAKTUS_FINDINGS_INTAKE_RATE`.
- `taktusctl findings` says what each lack is. `taktusctl findings review` is new.
- An instance that sent its findings through `TAKTUS_FINDINGS_CONNECTOR` alone sends nothing
  until its operator sets the level `automatic` or `review`.

## Where this promise ends
The list says what the release ships, not what an instance runs. An adapter the operator built
from the release's image under another name is classified by the release's name for it. A
worker that states its capabilities other than in `CAPABILITIES` is refused by the generator,
not guessed.

The vocabulary is a rule of thumb made exact. A capability the project names in a namespace the
product uses, such as `repository.wiki`, is a product candidate even where only the project's
own process asks for it. A capability the product should offer in a namespace it does not use
yet, such as `calendar.events`, is classified as the project's own and never leaves on its own.
Its operator reports it by hand. In review a person can call any candidate local; nobody can
call a local lack a candidate except by a report by hand.

A local lack reaches a person only where the tenant configured an owner-facing channel
(ADR-0106). Otherwise it is in `taktusctl alerts` and `taktusctl findings`, and nowhere else.

The signature proves that a submission came from the holder of a key. It does not prove who
that is. The owner's confirmation is what admits a sender, and the owner confirms by the
sender's identifier and the key's fingerprint, which the sender's operator must tell him
through a channel both trust. A submission captured and sent again is answered `known`. It
still counts towards the sender's rate. Five made-up keys can hold the
waiting places for new senders until the owner answers or ignores them. A key that leaks lets
its holder submit as that sender until the owner stops answering; there is no revocation yet
beyond leaving the intake closed.

The rate is counted from the ledger and is shared by every replica, but a burst inside one
check is not serialised: two submissions at once may both pass the last place. The intake
writes as the project's own app. What it writes is the intake's own sentences around closed
values, and the body of a report a person wrote, checked for the shapes of personal data only:
the intake does not hold the sender's tenant values. That check is made on the sender
(ADR-0112 §4).
