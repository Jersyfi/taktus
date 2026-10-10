Restoring means bringing an instance back to an earlier state, from a backup, without Taktus
doing it. Taktus must be repairable by a person when Taktus itself is broken. The way to do it
must be written down and practised (ADR-0013, requirement C).

**That way is not written down yet.** An instance installed today has no backup of its database.
Until one exists and a restore from it has been practised, an instance holds no real work.

What protects the data until then:

- `make down` stops the containers and keeps every volume. A volume is where a container keeps
  its data.
- No `make` target removes a volume. Removing one is always a person's own act, done by hand.

The rest of this page names what the cluster deployment does not cover yet, backups included.
