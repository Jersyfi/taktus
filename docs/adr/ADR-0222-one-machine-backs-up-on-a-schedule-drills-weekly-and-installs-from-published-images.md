# ADR-0222 — One machine backs up on a schedule, drills weekly, and installs from published images

**Status:** accepted · extends ADR-0087 (the backup program), ADR-0106 (a backup's outcome
told to the owner) and ADR-0174 (recovery objectives and the drill) to the single server ·
roadmap `1.0.0-beta`, "one server, no Kubernetes" (#445) · UC-10.5

## Context

The beta needs Taktus to install, upgrade and run on one machine from the guide alone. On a
cluster, the chart's two CronJobs back the instance up every day and drill the newest backup
every week (ADR-0174). On one machine nothing did either: the guide *Restoring* said that a backup
is two files taken by hand and that its recovery point has no bound. Docker Compose has no
scheduler. A business that runs its operation on one machine would lose everything since its
last manual backup.

The compose file also built every image from the checkout. The image workflow publishes scanned
and signed images on every version tag (ADR-0173), and an operator had no way to use them.

## Decision

### 1. The backup program schedules itself

`backup.py schedule` loops: a backup every `TAKTUS_BACKUP_EVERY_HOURS` (24 by default), and
after the backup of every `TAKTUS_DRILL_EVERY_DAYS` (7; 0 turns it off) a drill of the newest
backup. Each is the same command a person runs by hand, `backup` and `drill`. A failed round never
ends the loop; the next round runs at its time. The program stays standard library only and
imports nothing of Taktus (ADR-0013 C).

### 2. The compose file runs it beside the instance

The compose file gains the service `backup`, from the backup image, with the command `schedule`.
It reads the database through the instance's own secret, the stored files from the state volume
read-only, and writes into the volume `taktus-backups`, or a directory `TAKTUS_BACKUP_DIRECTORY`
names. The drill restores into a database server inside that container, never the instance's.
The recovery point objective of one machine is therefore the backup period: 24 hours by default.

### 3. A failed drill reaches the owner as a failed backup does

A backup records its outcome in `backup_outcome`, and the instance tells the owner of a failed
or missing one (ADR-0106). The schedule records a drill that did not verify the same way, as a
failed run at the step `drill`, under a name of its own one second after the backup's. The
instance's alert names the step: the restore drill of the newest backup did not verify its
ledger chains. The drill itself still never connects to the instance's database; the schedule
does, after the drill, as the backup does.

### 4. Published images, with the build as the fallback

The compose file names its images `${TAKTUS_IMAGE:-taktus:local}` and
`${TAKTUS_BACKUP_IMAGE:-taktus-backup:local}`. With `TAKTUS_IMAGE` set, `make up` pulls and
builds nothing, and `make start` pulls instead of building. Without it, both are built from the
checkout, as before.

## Alternatives

- **The host's cron.** It would need a person to install a line outside the repository's
  files, on every machine, and the guide could not check it. The schedule inside the compose
  file comes up with `make up`.
- **A drill that writes its outcome into the instance's database itself.** The drill would then
  connect to the database it is meant to be independent of. The schedule records the outcome
  after the drill ended, from outside it.
- **A separate table for drills.** The owner's alert already reads the backup's outcomes; a
  failed drill is a failed backup in the sense that matters, that the backup cannot be trusted.

## Consequences

- `deploy/backup/backup.py` gains `schedule` and the step `drill`; `ports/backups.py` and the
  alert's phrases know it.
- `deploy/docker/compose.yml` runs three containers; `make up` builds or pulls three images.
- `docs/guides/administration/restoring.md` states the single server's recovery point and the
  restore of a scheduled backup by hand.

## Where this promise ends

The period is a sleep between rounds, not a time of day: a machine that was off for a day takes
its next backup when it comes back, and none for the time it was off. The default volume lives on
the machine it backs up, and a disk that fails takes the backups with it; only a directory on
another disk or share keeps them off it, and the operator mounts that. A drill that fails is
reported until the next backup succeeds, because the alert reads the newest outcomes; the next
drill a week later reports it again if it still fails. The drill on one machine measures its
restore time and reports it, but `TAKTUS_DRILL_RESTORE_SECONDS` is not set by the compose file,
so it does not fail on time alone. Published images exist only once a release tag was pushed
with the repository's registry configured; until then the build from the checkout is the only
way.
