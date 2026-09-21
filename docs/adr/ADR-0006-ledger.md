# ADR-0006 — The ledger as a content-free hash chain

**Status:** accepted

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

## Where this promise ends

The chain is tamper-evident, not tamper-proof: a rewrite of the whole chain from a point onward
is detectable only against a copy of a hash taken earlier — a printed digest, an export, a
second instance — and the restore drill of the 1.0.0 roadmap is what makes that copy exist. The
ledger references content; when the referenced artifact is gone, the ledger still says what
happened but not what the value was. "Single source for every metric" holds for metrics Taktus
computes; a metric a person computes from an export is theirs.
