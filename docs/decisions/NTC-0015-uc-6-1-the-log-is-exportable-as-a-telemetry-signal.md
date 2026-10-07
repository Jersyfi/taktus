# NTC-0015 — UC-6.1: the log is exportable as a telemetry signal

**Mode entry:** M2.7
**Kind:** restoration
**Decided:** 2026-10-01
**Raised in:** [#52](https://github.com/Jersyfi/taktus/pull/52)
**How it follows:** the owner's project definition, version 2, UC-6.1: the log records which worker acted, is fed from the workers' event stream, and is exportable as a telemetry signal. Section 1 already requires which worker; the export was missing, so section 2 gains it and section 3 stops excluding it, keeping the distinction it drew between this record and the system's own telemetry.

## 1. What was decided

`docs/usecases/ledger/UC-6.1-the-complete-activity-log.md` was amended in three places.

- **Section 2** gains a condition: the log can be exported as a telemetry signal, entry by
  entry, with nothing the ledger itself would not carry.
- **"Proven so far"** names that export as not existing.
- **Section 3**, "Not an operational log", keeps the distinction between this record and the
  system's own log lines and traces, and says that exporting the record as a telemetry signal
  is in the use case.

## 2. The evidence

- DEC-0030 §4, second table, row UC-6.1.
- The owner's answer of 2026-10-01 (DEC-0041).
- None of the use case's eight named tests is touched; the condition describes an export that
  does not exist yet.

## 3. What was considered

- **Deleting "Not an operational log".** Rejected: the distinction holds — telemetry is not the
  record — and only the exclusion of the export contradicted the definition.
- **Folding the export into the existing export condition.** Rejected: one is an export for
  verification without Taktus, the other a signal to a telemetry endpoint; a test of one does
  not prove the other.

## 4. Which entry permits it

M2.7: bringing a use case up to the owner's own definition (DEC-0041). The amendment adds
nothing the definition does not ask; a requirement beyond it would be M3.15 and stays in
DEC-0030.
