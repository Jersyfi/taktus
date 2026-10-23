Restoring means bringing an instance back to an earlier state, from a backup, without Taktus
doing it. Taktus must be repairable by a person when Taktus itself is broken. The way to do it
must be written down and practised (ADR-0013, requirement C).

**On one machine**, a backup is two files taken by hand: the database and the stored files. The
page *Upgrading* gives the commands that take them (its section 1) and the commands that bring
them back (its section 5). Nothing takes such a backup on a schedule yet.

**On a cluster**, the chart's scheduled backup writes the database and the stored files to an
object store, and a person restores them by hand. The commands are in `deploy/k8s/README.md`,
section 11, *The restore, by hand*.

What protects the data in any case:

- `make down` stops the containers and keeps every volume. A volume is where a container keeps
  its data.
- No `make` target removes a volume. Removing one is always a person's own act, done by hand.

The rest of this page names what the cluster deployment does not cover yet.
