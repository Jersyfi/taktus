# ADR-0087 — The database is backed up by a job of the chart, and restored by hand

**Status:** accepted · makes ADR-0013 C hold for an installed instance (issue #67, roadmap
`0.1.0`)

## Context
ADR-0013 C requires that Taktus is repairable without Taktus: a manual way to restore an earlier
version exists, is documented and is exercised. The instance's database is its single source of
truth — runs, the ledger with its chain, the provenance of every result. On the target platform
its volume is bound to one node (`deploy/k8s/README.md` §9). Until now nothing backed it up.

The owner decided how backups are kept (DEC-0058): in a bucket off the node, without object
lock; **Taktus manages the retention itself, 30 days by default, configurable**; encryption is
an option, off by default. The credential may therefore delete, and the retention Taktus applies
is the only protection against keeping too much or too little.

Three questions were open: what takes the backup, in what form, and how a person restores it.

## Decision

### 1. A CronJob of the chart, from an image of its own, with no Taktus code in it
The chart renders the backup as a CronJob in the control plane's namespace (`backup.enabled`),
daily by default. It runs the backup image, `deploy/backup/Dockerfile`: the database's own image
with three standard tools added — `age`, `rclone` and `python3` — and one program of the standard
library, `deploy/backup/backup.py`. The program imports nothing of Taktus.

The backup is taken whether Taktus's roles run or not, and whatever state their code is in. A
backup that depends on a working Taktus would fail exactly when it is needed. The tools are the
ones a person restoring by hand uses, so the restore needs nothing the backup did not.

Two runs never overlap. A run that fails leaves its Job for its log, and the next run does not
wait for it.

### 2. One backup is a dump and a manifest under one name
A run writes two objects named after the time it started, `taktus-<UTC time>`:

- the **dump**, `pg_dump --format=custom` of the whole database, taken by a login that reads every
  row. Every tenant's table forces row-level security, so that login is the database's
  superuser or holds `BYPASSRLS`; with `database.deploy: true` the chart's login is the
  superuser;
- the **manifest**, a small JSON document: when, the dump's name, its SHA-256 and size, whether it
  is encrypted, the schema revision, and **every tenant's ledger head** — the last entry's `seq`
  and `hash` — read before the dump.

The ledger is append-only (ADR-0006), so every head read before the dump is in the dump. A
restore is checked against the manifest's heads: each tenant's chain must verify, and must reach
the head the manifest names. The hash of the head covers the whole chain before it.

### 3. Encryption to a public key, so that the instance cannot read its own backups
With `backup.recipient` set to an `age` public key, the dump and the manifest are encrypted to
it before they leave. The instance holds only the public key. The private key stays with the
operator, off the instance; without it no backup can be read, by the instance included. Off by
default, as the owner decided.

### 4. The retention is kept by the same run, after the backup is written
After a backup is written and listed in the store, every backup older than the retention is
deleted, its dump and its manifest, and no younger one. Two rules hold whatever the retention
says:

- **the newest backup is never deleted**, so that a retention of 0 keeps one, and a long stop of
  the schedule leaves the last backup there;
- **an object whose name is not of the program's form is never touched**, so the program deletes
  only what it wrote.

A run whose backup failed deletes nothing.

### 5. The restore is a procedure of standard commands
`deploy/k8s/README.md` §11 is the restore: list the backups, copy one out of the store, decrypt
it where it is encrypted, create the application role in an empty database, `pg_restore`, and
compare every tenant's ledger head with the manifest. Every step is a command of `rclone`,
`age`, `psql` or `pg_restore`; no step needs Taktus. `tests/deploy/test_backup_restore.py` runs
the same commands against a fresh database, with and without encryption, and verifies every
tenant's chain against the heads taken before the backup.

## Alternatives
- **A backup command in `taktusctl`, scheduled by Taktus's elected scheduler.** It would put the
  retention in Taktus's own code, which DEC-0058's wording reads well. It would also make the
  backup depend on the roles running and on the control plane image's code being sound — the
  failure that ADR-0013 C is about. The control plane image would need `pg_dump` too.
- **A volume snapshot of the database's disk.** On the target's node-local storage class there is
  no snapshot off the node, and a snapshot nobody has restored is not a restore path (§9).
- **Continuous archiving of the write-ahead log.** It restores to any point in time. It needs a
  base backup as well, a second tool to operate, and a restore a person can get wrong under
  pressure. A daily dump is what ADR-0013 C asks for; continuous archiving can come later without
  changing this.
- **Encryption with a key the instance holds** (symmetric, or `openssl` with a password). A
  compromised instance could then read every backup. A public key costs nothing more.
- **Retention by the store's lifecycle rules.** The owner decided against it (DEC-0058); it would
  also differ per provider.
- **An S3 client library in Python.** It would add a dependency to the program and to the restore
  path. `rclone` speaks to every S3-compatible store and to a directory, and a person can install
  it anywhere.

## Consequences
- `deploy/backup/Dockerfile` and `deploy/backup/backup.py`; the image is built and pushed with
  the release images (`.github/workflows/images.yml`) and runs in `tests/images.py`.
- The chart: `templates/backup.yaml`, a CronJob and its network policy; the database admits the
  backup; `backup.*` in `values.yaml`. The deployment identity must be allowed to manage
  `batch/cronjobs` (README §1).
- `CREDENTIALS.md`: the backup store's credential is one Secret with two keys, the identifier and
  the secret, mounted as files.
- `deploy/k8s/README.md` §11, the restore by hand.
- No migration, no contract change, nothing in `src/`.

## Where this promise ends
A backup is taken once a day by default; the work of the hours since the last one is lost with
the node. Nothing notices a backup that did not run or failed, beyond the failed Job the cluster
keeps: a missing backup is not yet a finding Taktus reports, and the owner sees it only by
looking. The restore is exercised by the tests against a database of the tests' own and was
carried out by hand once (`docs/runs/`); a restore of the installed instance's own backup is the
operator's, and the drill that repeats it on a schedule is S-03 of `1.0.0`. The retention keeps
the store from growing beyond what it says, not the store's own usage, and it deletes on the
store whatever the store's credential lets it delete: with a credential that may delete, a
compromised instance can delete its own backups (DEC-0058). Encryption protects what is in the
store; whoever holds the private key can read every backup, and a lost private key makes every
encrypted backup unreadable. The heads in the manifest are read before the dump: a tenant whose
first ledger entry was written between the two is in the dump and not in the manifest. Only the
database is backed up: the artifact volume (`state`) and the execution state claim are not.
