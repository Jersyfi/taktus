Restoring means bringing an instance back to an earlier state, from a backup, without Taktus
doing it. Taktus must be repairable by a person when Taktus itself is broken. The way to do it
must be written down and practised (ADR-0013, requirement C).

**On one machine**, the service `backup` of the compose file takes a backup every 24 hours: the
database's dump, the stored files and a manifest with every tenant's ledger head, in the volume
`taktus-backups` or the directory `TAKTUS_BACKUP_DIRECTORY` names (`deploy/docker/README.md`,
*Backups*). Every seventh day it restores the newest backup into a database of its own and checks
every tenant's chain against the heads the manifest noted: the restore drill. A failed backup and
a failed drill each reach the owner. To restore by hand, without Taktus:

```bash
docker compose -f deploy/docker/compose.yml run --rm backup list        # the backups kept
docker compose -f deploy/docker/compose.yml stop taktus
docker compose -f deploy/docker/compose.yml run --rm --entrypoint sh -v "$PWD:/out" backup \
  -c 'cp /backups/<name>.dump /backups/<name>.objects.tar.gz /out/'   # decrypt with age -d first if encrypted
```

`taktusctl backup list`, and the web app's page *Backup*, list the newest backups the backup
program recorded, each with how long ago it ran. Neither restores: a restore is this page's, by
a person.

Then bring the database back as the page *Upgrading* does in its section 5, with `<name>.dump`
in place of its dump. Bring the stored files back into the directory of objects, which the
archive holds flat:

```bash
docker compose -f deploy/docker/compose.yml run --rm --no-deps -T --entrypoint tar taktus \
  -xzf - -C /var/lib/taktus/objects < <name>.objects.tar.gz
make up
```

Compare every tenant's newest ledger entry with the heads in `<name>.json`; the drill makes the
same comparison on its own. A backup taken by hand before an upgrade
(*Upgrading*, section 1) is restored the same way.

**On a cluster**, the chart's scheduled backup writes the database and the stored files to an
object store, and a person restores them by hand. The commands are in `deploy/k8s/README.md`,
section 11, *The restore, by hand*.

**How much can be lost, and for how long** (ADR-0174). Two figures say it. The *recovery point
objective* is the longest stretch of recent work a loss of the database may take with it. The
*recovery time objective* is the longest time from the decision to restore until the instance
works again.

| Installation | Recovery point objective | Recovery time objective |
|---|---|---|
| One machine | 24 hours: one backup per `TAKTUS_BACKUP_EVERY_HOURS`, 24 by default; a shorter period bounds it shorter | 2 hours: the steps above and of *Upgrading*, section 5, for the two files of a backup |
| A cluster, daily backup | 24 hours | 4 hours |
| A cluster, with point-in-time recovery | 5 minutes by default | 4 hours |
| A cluster, highly available profile | that of its external database and its standby | minutes for a failover, 4 hours for a restore |

The time a person needs to notice a failure and decide is part of the objective and is not
measured. The machine's part is measured by the restore drill, on a cluster and on one machine
alike: it restores the newest backup every week, checks every tenant's ledger, and reports how
long its restore took; on a cluster it also fails when that took longer than its limit.
`deploy/k8s/README.md`, section 2, *Which profile*, gives each figure with the setting it follows
from.

**Point-in-time recovery** is an option on a cluster. The database then sends its record of
every change to the backup's store as it writes it, and an instance can be restored to any
moment since the oldest kept backup, not only to the moment of a backup. Its commands are in
`deploy/k8s/README.md`, section 11, *To a chosen moment, by hand*.

What protects the data in any case:

- `make down` stops the containers and keeps every volume. A volume is where a container keeps
  its data.
- No `make` target removes a volume. Removing one is always a person's own act, done by hand.

The rest of this page names what the cluster deployment does not cover yet.
