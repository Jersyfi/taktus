# NTC-0201 — A wait on the database ends with its reason

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-12
**Raised in:** the pull request for issue #309

## 1. What was decided

Two runs of one tenant in one process could block each other for good when a commit recorded
two ledger entries (issue #309, DEC-0187). The fix removes the process-wide lock from the
ledger; the store's claim on a tenant's chain is now the only lock on it. This notice records
the two changes of behaviour that come with the fix.

1. **A wait on the database ends.** Every connection of the PostgreSQL persistence adapter is
   opened with two server settings:
   - `lock_timeout` — how long a statement waits for a lock before it fails. The ledger's claim
     on a tenant's chain is such a lock. The setting is `TAKTUS_DATABASE_LOCK_TIMEOUT_SECONDS`,
     default 30.
   - `idle_in_transaction_session_timeout` — how long a transaction may sit open between two
     statements. After it, the server ends the session and releases its locks. The setting is
     `TAKTUS_DATABASE_IDLE_IN_TRANSACTION_SECONDS`, default 120.

   0 disables either. A transaction that runs into either fails with the server's reason and
   is rolled back; nothing it wrote is committed. Before, both waits had no end.
2. **The memory store claims a chain too.** Two transactions of one tenant in one process now
   record in turn: the second waits for the first to end, then reads its entries. Before, the
   process-wide lock covered only the read of the newest entry and the append. Two transactions
   that both recorded before either committed got the same sequence number, and the chain no
   longer verified. The memory store is for development and tests only.

## 2. The evidence

- `tests/integration/test_ledger_concurrency.py` starts two and four runs of one tenant at once
  through `RunEngine.start`, with a trigger and with a write that records `egress.write`. Before
  the fix, three of the four cases hung until the test's timeout of 30 seconds. After it, all
  four finish in about four seconds together, and the chain verifies.
- `tests/adapters/persistence/test_postgres_only.py` holds a chain in one transaction and shows
  that a second waits 0.3 seconds and then fails with "lock timeout". It also leaves a
  transaction idle past its timeout and shows that the server ends it with its reason and that
  nothing of it was committed.
- `tests/components/ledger/test_chain.py` shows, against the memory store, that two
  transactions of one tenant record in turn, and that a tenant waiting for its chain does not
  hold up another tenant. Both tests failed before the fix.

## 3. What was considered

- **A lock per tenant in the process instead of one for all.** Not taken: it still waits in the
  process while the database holds the claim, so the same deadlock returns between two
  transactions of one tenant.
- **Defaults equal to the lease (60 seconds) for both.** Not taken. A wait for the chain lasts
  as long as the transaction that holds it, and those take milliseconds. Thirty seconds is far
  above any legitimate wait and still fails a stuck one well inside a lease. A transaction idle
  between two statements is rarer, but a transaction may do work in the process between two
  of its statements. 120 seconds leaves room for that and still frees the locks of a
  transaction whose process stopped answering.
- **Setting the timeouts in the migrations, for the application role.** Not taken: an operator
  could then not tune them without a migration, and the development database would differ.

## 4. Which entry permits it

M2.4 of `docs/decisions/anchors.taktus.md`: "A change of what the software does, made inside an
agreed scope, that breaks no contract, moves no limit or autonomy level and says nothing
public." The scope is issue #309, which requires both timeouts on every connection. No contract
changes: the persistence port and the ledger port keep their signatures. No limit moves: the
timeouts bound a wait that had no bound, and they are operator settings, not budgets or
autonomy levels. Nothing public is said.
