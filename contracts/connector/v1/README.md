*Placeholder. Filled from `0.1.0`.*

One obligation is fixed before the contract is written (ADR-0022 §4): a connector that writes
outward, and a channel that delivers, records an `egress.write` or `egress.delivery` entry in
the ledger (`contracts/shared/v1/LedgerEntry.json`) naming what went out. That entry is what
makes "has this result left the system?" a question the ledger answers.
