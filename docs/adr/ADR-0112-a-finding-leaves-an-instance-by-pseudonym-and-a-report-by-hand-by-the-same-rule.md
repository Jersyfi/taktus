# ADR-0112 — A finding leaves an instance by pseudonym, and a report by hand by the same rule

**Status:** accepted · extends ADR-0046 (a lack of the product becomes a finding) and ADR-0008 (a free text is reflected back before it is acted on) · issue #446, UC-6.12, DEC-0201 · amended 2026-10-22 (ADR-0118): §1 records the level with the setting; §6 an instance outside the project submits, signed, to the intake of the project's own instance

## Context

DEC-0201 made a software business Taktus's first real customer. The business hosts its own
instance. Its findings and its bugs should improve the product. The project never acts on the
business's instance, and the business's data never reaches the project.

UC-6.12 already lets an instance outside the project raise findings in the Taktus repository.
It may do so only where its operator enabled it. A finding carries identifiers, causes,
durations and counts only. ADR-0046 built the path for any instance. Three things were missing
for an instance outside the project.

- **The identifiers of the instance left as they are.** A finding named the run and the step it
  was met in. A trigger derives a run's identifier (ADR-0035), and a process names its steps. Both
  can say something about the tenant. ADR-0046 said that a project whose identifiers say too much
  must not enable sending. That leaves the burden on the operator.
- **Nothing recorded that sending was enabled.** The setting `TAKTUS_FINDINGS_CONNECTOR` enabled
  it. Nothing on the instance said since when, or for which address.
- **No way to report by hand.** A bug a person notices left the instance only through whatever
  the person typed elsewhere. Nothing checked it for the tenant's data first.

## Decision

### 1. One setting, recorded in the tenant's ledger
Sending stays off by default. The operator enables it with one setting, `TAKTUS_FINDINGS_CONNECTOR`:
the address of a connector that serves `repository.issues` and `repository.comments`.

Each change of the setting is recorded in the ledger of every tenant whose findings it concerns,
as ADR-0104 records a tenant's creation. `finding.enabled` carries the channel's adapter and the
digest of the address the operator set. `finding.disabled` says that the setting is gone. The
entry is written before the first text is sent under the new setting. An instance that never
enabled sending records nothing.

### 2. Run and step leave by pseudonym
No finding carries a run's or a step's identifier as it is. It carries a *pseudonym* of each: an
HMAC-SHA-256 of the identifier under a key of the tenant. The run's pseudonym is `r-` and sixteen
hex digits. The step's is `s-` and twelve.

The same run always gives the same pseudonym, so the occurrences of a finding stay apart. The
same step gives the same pseudonym across runs, so the product sees that one step met the lack
again. Nobody without the key can compute a pseudonym from a guessed identifier.

The finding still states the run and the step where it was met (UC-6.12 §2). It states them by a
reference only the instance can resolve. `taktusctl findings` shows, below each finding and marked
as not sent, which run and step each pseudonym stands for.

### 3. The sender is random
A finding names its *sender*: one tenant of one instance. The sender's identifier is `src_` and
twenty hex digits, derived from the tenant's key. It is random. It names no person, no operator
and no tenant. A per-tenant sender keeps two tenants of one instance apart in public, as ADR-0104
keeps them apart in the ledger.

The key is drawn from the randomness port the first time a finding is shown or sent. It is kept
in the object store, as the instance keeps every artifact. The tenant's ledger records the digest
of it as `finding.source`. The first such entry whose key can be read holds, so two drawers at
once agree afterwards. The key never leaves the instance and is never logged.

Each occurrence says its sender, in its line and in its mark. The total of a finding says from
how many senders its occurrences came. One lack is one finding across instances, as it was
across runs: the lack's key is the same on every instance (ADR-0046 §4).

### 4. One rule for what may leave
A text that leaves for the product is made of two kinds of part. Some are the product's own: its
fixed sentences, closed values and pseudonyms. Others came from the instance: what was lacking,
the operator's form, and anything a person wrote. The rule checks every part that came from the
instance (`domain/service/leaving.py`). A part fails when it carries one of three things.

- **A value of the tenant.** That is every text and number its commands said and its runs were
  given, and every one their work states. The names of operations and capabilities a work calls
  are left out: they say what the process needs of the product, and a finding is about them. A
  value of at least five characters is matched as a whole, and so is each of its parts between
  commas, semicolons and line breaks. Both sides are folded to lower case first, with every run
  of punctuation made one space.
- **A shape of a personal or business datum.** An e-mail address, a telephone number, an IBAN, a
  card number, an amount with its currency, a street with its number, a postcode with its town.
- **A secret value the instance holds**, as the owner-facing channel checks (ADR-0045).

The rule is deterministic. It is a rule, never a probabilistic method (UC-6.12 §2).

A finding with a part that fails is not sent. It stays on the instance. `taktusctl findings`
shows it with what withholds it. The scheduler logs how many were withheld, never what withheld
them.

### 5. A report by hand
`taktusctl findings report --title TITLE --text FILE [--run RUN]` takes a report a person wrote: a
bug, an awkward flow, anything the rule over the blocks does not raise.

1. The text and the title are checked by the rule of §4.
2. A report that fails is not sent. The command says what it found, for the person alone.
3. A report that passes is shown exactly as it would be sent. Its body is the person's text,
   then the sender and, with `--run`, the run's pseudonym.
4. Where sending is not enabled, the command says so, and the person sends the text by hand.
5. Where it is enabled, the command asks to send it. It is sent only on the person's yes
   (ADR-0008: reflect back, then act).

The report opens an issue with the labels the operator configured for findings. Its idempotency
key derives from its text, so the same report sent twice opens one issue. The ledger records it
as `finding.reported`, with the digest of its text. It carries no mark: it is no finding, and no
later report adds to it.

### 6. Through a connector, by capability
Every text goes through the connector the setting names, by the operations of the capability
`repository` (CLAUDE.md §6). The connector acts as whatever identity its operator gave it. For
an instance outside the project, that identity needs the right to open issues in the Taktus
repository. Only the owner of the repository can grant it. ADR-0118 replaces this way for such
an instance: it submits, signed, to the intake of the project's own instance.

## Alternatives
- **Pseudonymise only on an instance outside the project.** Rejected: the product has no notion of
  "the project's instance" (ADR-0092). The project's own instance did not send findings yet, so
  nothing it sent changes.
- **Leave the identifiers and check them against the tenant's values.** Rejected: a step named
  after a customer whose name no run was given would pass. A pseudonym carries nothing at all.
- **A hash of the identifier without a key.** Rejected: an identifier is guessable. A plain hash of
  `invoice-mueller` is found by trying names.
- **One sender per instance.** Rejected: it would say in public which tenants share an instance.
  It would also need a table outside every tenant, which ADR-0104 avoided.
- **A table for the key, by migration.** Rejected for now: the ledger and the object store hold
  it without a new schema, and the ledger already answers "since when".
- **Check the whole text of a finding against the tenant's values.** Rejected: the product's
  fixed sentences would fail on ordinary values such as `worker`. The fixed sentences are the
  product's and carry nothing of the tenant.
- **A report by hand in the web app.** Not now: the command line is the operator's surface, and
  a finding a person raises from the run in the web app is a later part of UC-6.12. The rule and
  the service would be the same for both.

## Consequences
- `domain/service/pseudonyms.py`, `domain/service/leaving.py`, and the port `TenantContent`. The
  composition binds it to the run's and the command's repositories (`RunContent`).
- `ProductFindings` takes `Kept` (ledger, objects, unit of work, randomness, content, secrets).
  `Sending` takes the channel and the address the operator set. New: `pseudonyms`, `settle`,
  `outgoing`, `by_hand`, `send_by_hand`.
- The ledger gains `finding.source`, `finding.enabled`, `finding.disabled` and
  `finding.reported`. No migration.
- An occurrence and a mark carry the sender. A mark without one, written before, is still read.
- `taktusctl findings` shows the finding by pseudonym and, below it, what each stands for and
  what withholds it. `taktusctl findings report` is new.
- The scheduler asks every tenant at every interval even where sending is disabled, so that a
  change of the setting is recorded.

## Where this promise ends
The rule finds a tenant's value only where the instance holds it: in its commands, in what its
runs were given and in their work. A value that appears only in a step's result is not among them.
A personal datum the tenant does not hold is found only by its shape. A person's name alone has
no shape, so a report that names someone the tenant does not hold leaves. A value of fewer than
five characters is not matched. The shapes are those of German and international formats; a
postcode of another length or a street without its number is not one of them. The rule does not
read meaning: a description precise enough to identify a customer, without any value of it,
leaves.

What was lacking leaves as it is. It is a capability or an operation, which a process author
named. An author who names a capability after a customer the tenant holds is stopped by the
rule; one who names it after a customer the tenant does not hold is not.

The sender's key is as safe as the object store. A restore without the objects draws a new key:
the tenant then sends under a new sender, and its earlier pseudonyms no longer resolve. A
tenant's instance whose replicas do not share the object store would draw a key in each.

A pseudonym hides an identifier, not the timing. The times and durations of a finding still say
when a block began and how long it lasted.

The issue a report opens is written by the connector's identity. What the person writes in it
is theirs, and the rule cannot tell whether it names them. The repository is public, and what
its comments say is the commenters'.
