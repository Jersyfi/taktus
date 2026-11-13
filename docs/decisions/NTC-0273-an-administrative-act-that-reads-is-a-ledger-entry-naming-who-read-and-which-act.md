# NTC-0273 — An administrative act that reads is a ledger entry naming who read and which act

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-11-13
**Raised in:** branch `area/admin` (final round before 1.0, concept mode, DEC-0236)
**How it follows:** UC-10.2 §2 says "Every administrative act, by whatever path, is a ledger
entry naming the identity that did it, the act and its target." The inventory of administrative
acts (ADR-0279) names reads among its acts: a list of tenants, of channel links, of rights, of
quotas, the structure, where something is filed, the register, the backup's listing and the
instance's health. The requirement makes no exception for them, so the strict reading follows.
Strict in substance, sparing in ceremony: the entry is content-free, as the ledger is, and it
records nothing of what was read.

## 1. What was decided

Every act of the inventory that reads leaves `administration.read` on the ledger of the tenant it
read. The entry names the identity in `refs.actor` and the act by its inventory name in
`refs.action`, and carries no digest. Both ways in write it through one function,
`read_recorded` of `adapters/driving/inventory.py`. On the command line the reader is
`--identity`, `operator` by default. On the HTTP surface the reader is the identity the key or
the session proves, and `administrator` for the holder of the instance's administration key,
which names no identity, as an export already records (ADR-0221). `tenant.list` reads every
tenant, so it leaves one entry on each tenant's ledger. A read that the ledger did not take is
refused on the command line.

An act asked in dialogue leaves `administration.prepared` when its plan draft is opened. That
makes preparing an update of Taktus an entry too, before anything is commissioned (ADR-0296).

## 2. The evidence

- `tests/adapters/rest/test_administration_ledger.py`: the test walks the inventory, does each
  act on the HTTP surface and finds its entry naming who did it. The three acts that need a
  database or the run engine name the test that finds their entry there.
- `tests/integration/test_instance_command.py::test_every_act_that_reads_is_a_ledger_entry_on_the_command_line`:
  each read on the command line leaves its entry, naming the act and `--identity`, with no
  digest.

## 3. What was considered

- **The inventory separates reads from acts, and reads are not entries.** Rejected: that would
  narrow UC-10.2 §2 to become meetable, which `CLAUDE.md` §11 point 13 forbids.
- **The entry carries a digest of what was read.** Rejected: a digest of an answer says nothing
  a person can use, and the ledger records that something happened, not its content.
- **A web page's every view records a read.** Rejected for pages outside the inventory: only an
  administrative act is required to be an entry.

## 4. Which entry permits it

M2.6: a matter in neither anchor list, decided from the source, UC-10.2 §2. The owner may
overrule it in the pull request.

## 5. The entry it proposes

M1.29: *an administrative act that reads is recorded as `administration.read`, content-free.* It
belongs among the mode-1 entries of `docs/decisions/anchors.taktus.md`, as the default every
tenant inherits.
