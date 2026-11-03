# ADR-0006 — The ledger as a content-free hash chain

**Status:** accepted · amended 2026-10-18 (ADR-0105): a projection derived from the ledger, which records the last sequence number it read and is rebuilt from the ledger at any time, is allowed; the ledger stays the one source · amended 2026-10-31 (ADR-0164): each run has its own chain, anchored in the tenant's chain

## Context
The activity log carries three jobs at once: compliance evidence, the basis for every metric, and
fault analysis. It must be tamper-evident without that property depending on secrecy — the
repository is public and installations sit with customers.

## Decision
Entries chained by hash. The ledger **references** content, it does not store it: no personal data,
no secrets, no payloads. It is the single source for every metric — no view and no value ledger
computes from a second source.

## Alternatives
- **A plain append-only log** — enough for debugging, not for a compliance record.
- **An external audit platform** — would become a core dependency and break the removal test.
- **Storing content** — convenient for debugging, a GDPR liability and a secret-leak risk.

## Consequences
- Fault analysis goes via referenced artifacts. Intended.
- There are never two truths about what happened.

## Amendment — a chain per run (2026-10-31)

ADR-0164 changes what a link is. An entry is linked to the entry before it in its run's chain,
or in the tenant's chain when it references no run. The heads of the run chains are anchored in
the tenant's chain as a Merkle root. The hash rule keeps its form; every entry written before
keeps its hash and its place on the tenant's chain. The ledger is still content-free, still the
single source of every metric, and still never edited.

## Where this promise ends

The chain is tamper-evident, not tamper-proof: a rewrite of the whole chain from a point onward
is detectable only against a copy of a hash taken earlier — a printed digest, an export, a
second instance — and the restore drill of the 1.0.0 roadmap is what makes that copy exist. The
ledger references content; when the referenced artifact is gone, the ledger still says what
happened but not what the value was. "Single source for every metric" holds for metrics Taktus
computes; a metric a person computes from an export is theirs.
