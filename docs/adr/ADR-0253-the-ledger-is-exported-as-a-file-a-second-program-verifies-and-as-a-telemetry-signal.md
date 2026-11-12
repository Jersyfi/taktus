# ADR-0253 — The ledger is exported as a file a second program verifies, and as a telemetry signal

**Status:** accepted · extends ADR-0006, ADR-0164, ADR-0174 §3 · UC-6.1 · DEC-0228

## Context

UC-6.1 requires that the chain can be exported and verified outside Taktus, by anyone with the
export and the documented hash rule, without Taktus running; and that the log can be exported
as a telemetry signal, entry by entry, with nothing the ledger itself would not carry. The hash
rule is published in `taktus.components.ledger`. The backup program, which imports nothing of
Taktus, already walks a restored database's chains by that rule (ADR-0174 §3). Neither an export
of the ledger nor a signal of it existed.

## Decision

### 1. The export is one entry per line

`GET /ledger/export` answers every entry of the reader's tenant, in sequence order, one JSON
document per line (`application/x-ndjson`), each the document its hash covers. Only the role
`owner` exports: the ledger holds every run of the tenant, also those a given reader may not
see. The entries carry identifiers, tokens and digests, no text (ADR-0006), so the file holds no
content either.

### 2. A second program verifies it

`deploy/backup/backup.py verify-export <file>` walks the file by the published rule with the
walk the drill uses: sequence numbers rise, every chain's places and links hold, every hash
recomputes, every anchor matches the heads it covers. It needs no database and no instance, and
imports nothing of Taktus. Every finding is printed with its sequence number; the exit code is 0
only for an intact chain. The order is the file's, so a line moved is found.

### 3. The signal is a span per entry

The scheduler's leader reads each tenant's committed entries above the place it reached, up to
the stable head (ADR-0164), and emits each as one span `ledger.entry` through the telemetry port.
Its attributes are the entry's fields, `ledger.<field>`, with its references and consumption one
level down, and nothing else. It starts at the head it finds at its first look; the history is
the file's.

## Alternatives

- **One JSON document holding every entry.** A line per entry streams, and a tool that reads
  lines needs no parser for the whole.
- **A verifier inside `taktusctl`.** It would import Taktus's own rule, so a fault in the rule
  would verify itself. The backup program is the second implementation already held to the
  first (`tests/deploy/test_drill_chain.py`).
- **Emit the span when the entry is recorded.** The transaction may still roll back, and the
  signal would carry an entry that never existed.

## Consequences

- An auditor with the file and the rule verifies the ledger on a machine of their own.
- An operator's telemetry backend receives every new ledger entry within seconds.

## Where this promise ends

- **Not a view.** Who sees which part of the log is `reporting`'s (UC-6.4); the export is the
  owner's whole tenant.
- **Not the record.** A span the backend lost is still in the ledger; the signal is at most once
  per instance's life, and after a restart it starts again at the head.
- **Not the content.** An export holds no document a step read; that lives where it lives.
- **Not signed.** The chain proves that nothing was altered after its head was taken; holding
  the head somewhere the instance cannot write is the anchor's and the backup's (ADR-0164,
  ADR-0174).
