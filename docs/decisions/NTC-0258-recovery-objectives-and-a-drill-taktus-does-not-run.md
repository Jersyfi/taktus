# NTC-0258 — The recovery objectives per profile, and a drill Taktus does not run

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-31
**Raised in:** branch `concept/package-d--recovery` (package D, concept mode, DEC-0222), for issue #346
**How it follows:** issue #346 asks each profile to state its objectives, and gives no figures. ADR-0013 calls Taktus business-critical and asks for repair without Taktus (C); ADR-0087 already takes a backup daily and reports one older than 26 hours (ADR-0106). The figures below follow from what is configured, not from a wish: the recovery point is the backup's schedule or the archive's timeout; the recovery time is what the steps of a restore by hand need, with the machine's part measured. That the drill is not a Taktus process follows from ADR-0013 C the way ADR-0087 put the backup outside Taktus. Where a looser and a stricter reading were both consistent, the stricter one in substance was taken.

## 1. What was decided

- **Recovery point objective:** 24 hours with the daily backup; `archiveTimeoutSeconds`,
  5 minutes by default, with point-in-time recovery; the external database's for `ha`; on one
  machine, unbounded until the operator schedules a backup — said as such.
- **Recovery time objective:** 4 hours on a cluster, of which the machine's part at most
  `backup.drill.restoreMinutes`, 60 by default, beyond which the drill fails; 2 hours on one
  machine for the two files of *Upgrading* §5. A person's part is stated, not measured.
- **The drill, S-03, runs from the chart's scheduler and has no bundle.** A drill that needs
  Taktus to run shows nothing about repairing Taktus without it.
- **With encryption, the drill in the cluster needs the private key, and the chart requires it
  to be named.** The documentation recommends running the drill off the instance then; the
  chart never places the key by default.
- **The archive timeout defaults to 300 seconds**, PostgreSQL's commonly used value between a
  segment per minute (heavy on a store for a quiet instance) and the server's own default of
  none (no bound at all).

## 2. The evidence

ADR-0013, ADR-0087, ADR-0106; `deploy/k8s/README.md` §2 *Which profile* and §11; the drill's
measured restores in `tests/deploy/test_point_in_time.py`, which take seconds on a test
database, so that an hour for the machine's part leaves the rest of four hours to the person.

## 3. What was considered

- **Smaller objectives, an hour to restore.** Not taken: a person who must notice, decide and
  type the steps of §11 at night cannot be promised in an hour by software.
- **No figure, "depends on the installation".** Rejected: the issue asks for the figures, and an
  operator cannot plan around "it depends".
- **S-03 as a bundle with a worker that runs the restore.** Rejected for the reason in §1.

## 4. Which entry permits it

M2.6, deciding within the vision's direction where the sources give it; the owner may overrule
any figure in the pull request.

## 5. The entry it proposes

**M2.11** — *A figure the product states about its own operation — an objective, a default
limit, an interval — set from what the configuration already implies and what a person can carry
out by hand, stated with the setting it follows from; the owner may overrule it in the pull
request.*
