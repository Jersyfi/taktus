# 2026-10-11 — The first restore, by hand

The backup of #67 (ADR-0087) taken from a running Taktus and restored onto an empty database by
the steps of `deploy/k8s/README.md` §11, carried out one by one by a session, not by the test.
ADR-0013 C asks for a restore path that is documented **and exercised**; this is the first
exercise. The restore of the installed instance's own backup follows NEED-0025.

## What ran

| | |
|---|---|
| Source | Taktus self-hosted with `deploy/docker/compose.yml` and the reference worker, project of its own, PostgreSQL 16; one tenant, `default`; four runs submitted, ledger at `seq` 17 |
| Backup | the backup image as the chart's CronJob runs it (`deploy/backup/Dockerfile`, the content of this pull request), against the source's network, the store a directory (`TAKTUS_BACKUP_STORE_DIRECTORY`), not encrypted |
| Target | a fresh `postgres:16-alpine`, nothing in it but its login |
| Tools of the restore | `rclone`, `psql`, `pg_restore` from the backup image, run as a shell — what a person would type |

## What happened, step by step

1. **Backup**, 2026-10-11 18:33:10 UTC: one dump of 79 534 bytes and its manifest, `1 tenant(s)`;
   the manifest's head for `default`: `seq` 17.
2. **Work after the backup**: one more run submitted; the source's ledger went to `seq` 22. The
   restore must end at 17, not at 22.
3. **§11 step 2** — listed the store, copied both objects out; `sha256sum` of the dump equal to
   the manifest's `sha256`.
4. **§11 step 4** — the application role created and granted: `DO`, `GRANT ROLE`.
5. **§11 step 5** — `pg_restore --no-owner --exit-on-error --single-transaction`: no error.
6. **§11 step 6** — the head as the restored database holds it: `default|17|sha256:a27f…4ab2`,
   equal to the manifest's. The schema revision `0049`, equal to the manifest's.
7. **The chain**, verified by Taktus's own ledger code against the restored database: 17 entries,
   intact, no finding, head `seq` 17 with the same hash.
8. **§11 step 7** — the control plane image started on the restored database with the role `api`:
   `/ready` answered `ready`.

Every check held. Nothing was changed in §11 for the steps to work.

## What it does not show

- The store was a directory, not the object store: the object store's mode is held by
  `tests/deploy/test_backup_restore.py` against an S3 interface, and on the platform by NEED-0025.
- Not encrypted: the encrypted restore is held by the same test, with and without the key.
- One tenant: two are held by the test.
- The source was a development deployment; the instance's own backup is restored under NEED-0025.

## The instance's own backup, 2026-10-12

After the upgrade to `v0.2.0-rc.4` (NEED-0025) the CronJob's first runs failed: the database
refused `psql` in the first seconds of each new pod, while the cluster applied its network policy
to it; a probe with the backup's labels was answered from the fifth second on. The fix is #266.
A backup started by hand with ten seconds' delay wrote `taktus-20261012T060426Z` (138 581 bytes,
one tenant). The steps of §11, carried out on the workstation with the store's credential:

- the store listed the backups under `instance/`; both objects copied out; the dump's SHA-256
  equal to the manifest's;
- the role created and granted; `pg_restore` without error into an empty `postgres:16-alpine`;
- the head of `default`: `seq` 139, the hash the manifest names; schema revision `0049`.

## Frictions

- `make verify-compose` stops at its second step since #82: `taktusctl submit` without
  `--identity` is refused, and the script submits without one. The runs here were submitted with
  the identity the script had created. Issue #250.
