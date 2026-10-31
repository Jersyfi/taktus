Restoring means bringing an instance back to an earlier state, from a backup, without Taktus
doing it. Taktus must be repairable by a person when Taktus itself is broken. The way to do it
must be written down and practised (ADR-0013, requirement C).

**On one machine**, a backup is two files taken by hand: the database and the stored files. The
page *Upgrading* gives the commands that take them (its section 1) and the commands that bring
them back (its section 5). Nothing takes such a backup on a schedule yet.

**On a cluster**, the chart's scheduled backup writes the database and the stored files to an
object store, and a person restores them by hand. The commands are in `deploy/k8s/README.md`,
section 11, *The restore, by hand*.

**How much can be lost, and for how long** (ADR-0174). Two figures say it. The *recovery point
objective* is the longest stretch of recent work a loss of the database may take with it. The
*recovery time objective* is the longest time from the decision to restore until the instance
works again.

| Installation | Recovery point objective | Recovery time objective |
|---|---|---|
| One machine | everything since the last backup taken by hand: nothing takes one on a schedule, so there is no bound until the operator schedules one | 2 hours: the steps of *Upgrading*, section 5, for the two files of a backup |
| A cluster, daily backup | 24 hours | 4 hours |
| A cluster, with point-in-time recovery | 5 minutes by default | 4 hours |
| A cluster, highly available profile | that of its external database and its standby | minutes for a failover, 4 hours for a restore |

The time a person needs to notice a failure and decide is part of the objective and is not
measured. The machine's part is measured on a cluster: the restore drill restores the newest
backup every week, checks every tenant's ledger, and fails when it took longer than its limit.
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
