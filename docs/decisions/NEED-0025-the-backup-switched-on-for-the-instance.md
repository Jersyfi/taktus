# NEED-0025 — The backup switched on for the instance

**Kind:** action
**Raised in:** the pull request for issue #67, which adds the backup to the chart
**Issue:** [#251](https://github.com/Jersyfi/taktus/issues/251)
**Needed by:** 2026-10-20
**Foreseeable since:** #67, whose backup is a CronJob the deployment identity may not yet create

## 1. What is needed

Three acts on the platform that only you can do, after the pull request for #67 is merged:

1. **The deployment identity may manage cron jobs** in the control plane's namespace: one line
   added to its Role, applied by you.
2. **A release that carries the backup image**: a release candidate tagged on `main`, as for the
   earlier ones (M3.6), so that the image workflow builds and pushes `taktus-backup` with the
   others.
3. **Your yes to the session upgrading the instance** with the backup switched on, or the upgrade
   run by you with the install script, followed by one backup started at once and its restore
   checked on your workstation.

## 2. Why

ADR-0013 C requires a manual way to restore an earlier version, documented and exercised. The
pull request for #67 adds both: the backup as a CronJob of the chart (ADR-0087) and the restore
as commands a person runs (`deploy/k8s/README.md` §11), exercised against a database of the
tests' own. The instance's own database is backed up only once the CronJob runs there.

Until then, the instance's ledger lives on one disk of one node. NEED-0009 said what follows:
the instance holds no real work, and no process's autonomy is raised there. #87 — Taktus running
its own processes on the instance — makes it hold real work.

## 3. By when

**2026-10-20**, and in any case before #87 is taken up. If it is not there by then, #87 waits:
the session does not start real work on an instance without a backup.

## 4. How to provide it

1. **Allow cron jobs.** In the Role of the deployment identity in the control plane's
   namespace, add `cronjobs` beside `jobs` in the rule for the API group `batch`, with the same
   verbs, and apply it as you applied the Role on 2026-10-08 (NEED-0007). The deployer's file in
   your private configuration directory holds the Role; the session has written the line there
   for you to check.
2. **Tag a release candidate** on `main` after the merge, the next after `v0.2.0-rc.3`. The image
   workflow builds and pushes `taktus-backup` beside the other images.
3. **Decide on encryption.** Off by default (DEC-0058). To switch it on, make a key pair on your
   workstation with `age-keygen -o <file>`, keep the file in your secret store and nowhere on the
   instance, and give the session the public key it prints (`age1…`) — a public key may be
   written into the instance's private values; the private key never.
4. **Say so in the issue**, with your permission for the session to upgrade the instance with the
   deployment identity, or run the install script yourself with the new tag. The session has
   added the backup's values to the instance's private values: the store's address and bucket
   from your private note, the existing secret `taktus-backup-store` with its two keys, and the
   prefix `instance/`.

## 5. What it must never be

- **Never a ClusterRole or a right outside the two namespaces.** Cron jobs in the control plane's
  namespace, nothing more.
- **Never the private key of the encryption on the instance**, in a values file, a Secret or this
  repository. The instance holds the public key only.
- **Never the store's address in this repository.** It is in your private note and the
  instance's private values.

## 6. What happens next

Write in this issue: **"NEED-0025 is provided."** The next session records it first, upgrades
the instance (or checks your upgrade), starts one backup at once, and restores it on the
workstation into a fresh database by the steps of §11, comparing every tenant's ledger head with
the manifest. The result goes to `docs/runs/`, beside the exercise of #67.

## 7. How to confirm

- `kubectl auth can-i create cronjobs` as the deployment identity in the control plane's
  namespace answers `yes`, and in the execution namespace `no`.
- After the upgrade the CronJob `<release>-backup` exists, and the job started from it ends
  `Complete`; its log names the backup and the number of tenants, and no secret.
- The store lists two objects under `instance/`, `taktus-<time>.dump` and `.json`.
- The restore of §11 on the workstation ends with every tenant's head equal to the manifest's.

## Outcome

**Provided:** 2026-10-12
**Confirmed by:** `kubectl auth can-i create cronjobs` as the deployment identity answers `yes` in the control plane's namespace and `no` in the execution namespace; after the upgrade to `v0.2.0-rc.4` the CronJob `taktus-backup` exists; a backup started from it ended `Complete` and wrote `taktus-20261012T060426Z.dump` and `.json` under `instance/` in the store; and the restore of `deploy/k8s/README.md` §11, carried out on the workstation from the store into an empty database, ended with the tenant `default` at `seq` 139 and the hash the manifest names, the dump's SHA-256 equal to the manifest's and the schema revision `0049`. The first runs started from the CronJob were refused by the database in their first seconds; the fix is #266, and until it is released the first backup was started by hand with a delay of ten seconds before the program.
**How it was provided:** step 1 by the owner on 2026-10-11 (the Role applied); step 2, the tag `v0.2.0-rc.4`, by the session under DEC-0174; step 3, no encryption, the owner's answer; step 4, the upgrade with the install script, by the session under DEC-0179 and the owner's explicit permission of 2026-10-12.
**Recorded in:** the pull request that makes the backup wait for the database (#266)
