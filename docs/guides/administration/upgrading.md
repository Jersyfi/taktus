# Upgrading

Upgrading takes an instance from its release to the next one. Every run keeps its place: a
finished run stays finished, and a run that waits — for a person, for time to pass, after a halt
or an escalation — continues after the upgrade at the step where it stopped. Each release is
tested for exactly that, from the release before it (section 4).

**Upgrade one release at a time.** The promise covers one step: the previous release to the
next. An upgrade that skips a release may need the instance to stop for longer.

## 1. Before every upgrade: a backup

A **backup** is a copy of the instance's data from which it can be brought back. Take one
before every upgrade. It is the way back if the upgrade fails.

**On one machine**, from the directory of the repository, write the database and the stored
files into two files of this directory:

```bash
docker compose -f deploy/docker/compose.yml exec -T postgres pg_dump -U taktus --format=custom taktus > taktus-before-upgrade.dump
docker compose -f deploy/docker/compose.yml exec -T taktus tar -czf - -C /var/lib/taktus . > taktus-before-upgrade-state.tar.gz
```

Move both files off the machine. The page *Restoring* says how they are brought back.

**On a cluster**, the chart's scheduled backup writes the database to an object store when
`backup.enabled` is set (`deploy/k8s/README.md`, section 11). Run one now, and wait until it
completed:

```bash
kubectl -n taktus create job --from=cronjob/taktus-backup taktus-backup-before-upgrade
kubectl -n taktus wait --for=condition=complete job/taktus-backup-before-upgrade --timeout=30m
```

Without a scheduled backup, take a copy of the database by hand:

```bash
kubectl -n taktus exec statefulset/taktus-database -- pg_dump -U taktus --format=custom taktus > taktus-before-upgrade.dump
```

## 2. On one machine

```bash
git fetch --tags
git tag --sort=-creatordate | head -1
git checkout <the tag it printed>
make up
```

`make up` builds the new image and replaces the Taktus container. Before it stops, the old
container lets each running step reach its boundary, within five minutes at most. The new one
brings the database to the new schema when it starts. The command returns once the new release
answers that it is ready. Your files under `deploy/docker/secrets/` and `deploy/docker/taktus.env`
stay as they were.

## 3. On a cluster

Build and push the new release's image as in *Installing from nothing*, section 3.2, with the
new `<version>`. Change `image.tag` in your `taktus-values.yaml` to it, and upgrade:

```bash
git fetch --tags
git checkout <the new tag>
.tools/bin/helm upgrade taktus deploy/k8s/chart --namespace taktus -f taktus-values.yaml --wait --timeout 10m
```

Helm first runs the job that brings the database to the new schema, and starts the new release
only when that job succeeded. A failed job leaves the old release running and the upgrade
failed; `kubectl -n taktus logs job/taktus-migrate` says why.

## 4. After the upgrade

Check that the instance is ready and that its runs are where they were:

```bash
curl -fsS http://127.0.0.1:8080/ready
docker compose -f deploy/docker/compose.yml exec taktus taktusctl ledger verify --tenant <tenant>
```

On a cluster, the second command is `kubectl -n taktus exec deploy/taktus-all -- taktusctl ledger
verify --tenant <tenant>`. It checks that the tenant's record of everything that happened is
unbroken.

The web app shows every run where it was before. A run that waits for a person still waits for
the same step. A run that halted at its money limit continues when a person raises the limit
(`taktusctl resume --run <run> --raise <amount> --reason "<why>"`). A run that escalated
continues from the step that failed, once its cause is removed
(`taktusctl run --process <bundle> --resume <run>`). A run in a long wait wakes at its time.

Each release carries the test of exactly this: `deploy/docker/upgrade.sh` starts the previous
release, leaves a run finished, one waiting for a person, one in a long wait, one halted at its
money limit and one escalated, upgrades to the new release, and continues each of them to its end.
A step that had completed before the upgrade never runs again.

## 5. If the upgrade fails

Do not remove a volume. Bring the previous release back from the backup of section 1.

**On one machine**, with the two files of section 1 in the repository's directory. These
commands replace the instance's database and stored files by the backup's: whatever happened
after the backup is lost.

```bash
git checkout <the previous tag>
docker compose -f deploy/docker/compose.yml stop taktus
docker compose -f deploy/docker/compose.yml exec -T postgres psql -U taktus -d postgres -v ON_ERROR_STOP=1 -c 'DROP DATABASE taktus' -c 'CREATE DATABASE taktus OWNER taktus'
docker compose -f deploy/docker/compose.yml exec -T postgres pg_restore -U taktus -d taktus --no-owner --exit-on-error --single-transaction < taktus-before-upgrade.dump
docker compose -f deploy/docker/compose.yml run --rm --no-deps -T --entrypoint tar taktus -xzf - -C /var/lib/taktus < taktus-before-upgrade-state.tar.gz
make up
```

**On a cluster**, `.tools/bin/helm rollback taktus --namespace taktus` brings the previous
release's objects back, but not its database's schema. Restore the database from the backup
first, as `deploy/k8s/README.md`, section 11, *The restore, by hand*, describes.
