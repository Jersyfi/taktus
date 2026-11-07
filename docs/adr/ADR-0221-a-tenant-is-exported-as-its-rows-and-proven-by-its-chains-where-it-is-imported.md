# ADR-0221 — A tenant is exported as its rows, and proven by its chains where it is imported

**Status:** accepted · builds on ADR-0020 (a tenant in every row), ADR-0104 (the registry),
ADR-0164 (a chain per run) and ADR-0165 (the object store) · roadmap `1.0.0`, "data export
proven by re-import" · UC-10.6

## Context

The roadmap's condition for `1.0.0`: an export of a tenant — processes, runs, ledger,
provenance, artifacts — is imported into a fresh instance, and the ledger chain and every
provenance chain verify there. Principle 13 asks the same in other words: a business can leave
with its data. Nothing could do it. A backup restores a whole instance to a moment (ADR-0174);
it cannot move one tenant out of an instance that serves several.

A tenant's state lives in about sixty tables of the database, each with the tenant in its key
(ADR-0020), and in the object store, whose objects the rows name by digest (ADR-0165). The
ledger's entries carry their sequence number, their place in a chain and a hash over both; an
entry written back with another number breaks the chain.

## Decision

### 1. An export is every row with the tenant's name, and every object those rows name

The port `TenantArchive` reads every store of a tenant as rows and writes them back. Its
database adapter takes every table that carries `tenant`, from the schema's metadata, so that a
table a migration adds is in the export without a change of the adapter. It leaves out five,
each for its reason: the registry's row (the import adds it from the export's entry), the
ledger's projections (derived, rebuilt from the ledger), sign-in sessions and link codes
(bound to the instance they were made on), and the backup program's outcomes (the old
instance's). A row leaves without its tenant and without a column the database generates; its
values become JSON by their column's type and are read back by the same type.

The export document holds the tenant's registry entry, the rows by store, the bytes of every
object whose digest appears in any row, the digests named but not held (erased on a
data-protection request, ADR-0176), and what the chains looked like: the number of entries, the
newest hash of the tenant's chain and of every run's, and whether the ledger verified. Its last
field is its own digest over everything else.

### 2. An import writes into a tenant that holds nothing, then checks it there

An import refuses a document whose digest does not match, an object whose bytes do not hash to
its name, and a tenant of which the instance holds even one row. A fresh instance's `default`
tenant holds none, and is the place an export of `default` goes. The objects are written first,
then every row in one transaction, parents before children. The ledger's sequence is shared by
every tenant of a database, so the import moves it past the highest number it wrote.

The check runs where the tenant now lives: the ledger verified from its first entry, the same
number of entries as the export names, the same newest hash on every chain, and every run's
provenance chain verified against its ledger entries. The import is then recorded on the
tenant's ledger, `tenant.imported` with the export's digest and whether it verified. An export
is recorded the same way, `tenant.exported`, after it was read.

### 3. It is reached three ways

`taktusctl tenant export <tenant> --out <file>` and `taktusctl tenant import <file>`, which
exits 1 when a check fails. On the HTTP surface, for the instance's administration key only:
`GET /administration/tenants/{tenant}/export` and `POST /administration/tenants/import`. Both
need the database. An instance whose state is files is development state and says so.

## Alternatives

- **An export through the repositories, aggregate by aggregate.** It would carry a tenant from a
  development instance's files to a database too. It would also need every store's reading and
  writing taught to it — the queue, the traces, the outbox — and would miss the next store
  added. The table walk misses none, and the database is where an operated instance lives.
- **The database's own dump with a filter per tenant.** `pg_dump` has no row filter; a copy
  per table by hand would be the same walk without the type handling and the check.
- **Renumbering the ledger into the target's sequence.** It would break every hash. The numbers
  are kept, and the sequence moves.

## Consequences

- `ports/persistence.py` gains `TenantArchive`, `ArchivedRows`, `TenantNotEmpty` and
  `TenantImported`; `adapters/driven/postgres/archive.py` implements the archive;
  `composition/tenant_export.py` writes and reads the document.
- The export holds the tenant's data in clear, its identities' key digests among it. It is kept
  as a backup is kept; the guide says so.
- `tests/integration/test_tenant_export.py` exports a tenant with a finished and a waiting run
  from one database, imports it into a fresh one and checks it entry for entry; the waiting run
  continues there.

## Where this promise ends

The check proves the imported tenant is the exported one; it does not prove the exported one
was right, and an export whose ledger did not verify says so and is imported as it is. An
import is not undone by Taktus: a check that fails leaves the rows written, and the operator
removes the tenant's rows or the database, as they would after a failed restore. The export is
one document read into memory whole: a tenant whose objects do not fit the machine's memory is
not exported by it, and no limit below that is enforced. Two instances on different schema
versions are not bridged: the import reads the stores of its own schema and refuses a store it
does not have, so an export is imported into an instance of the same release or one whose
migrations kept every store. Nothing is encrypted by the export itself.
