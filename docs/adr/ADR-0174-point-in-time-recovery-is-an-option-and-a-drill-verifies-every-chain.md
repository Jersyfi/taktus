# ADR-0174 — Point-in-time recovery is an option, each profile states its objectives, and a drill verifies every chain

**Status:** accepted · extends ADR-0087 (the backup by a job of the chart) and ADR-0013 C (repair
without Taktus) · issue #346, UC-10.5

## Context

ADR-0087 backs the database up once a day with `pg_dump` and restores it by hand. It named
continuous archiving of the write-ahead log as an alternative that "can come later without
changing this". The write-ahead log (WAL) is PostgreSQL's record of every change, written before
the change is applied, in files of 16 MiB called **segments**. A **base backup** is a copy of the
database's files taken while it runs. A base backup and every segment archived after it restore
the database to any moment the segments cover. That is **point-in-time recovery**.

Two figures say what a backup is worth. The **recovery point objective** (RPO) is the longest
stretch of recent work a loss of the database may take with it. The **recovery time objective**
(RTO) is the longest time from the decision to restore until the instance works again. The
chart's three profiles (`small`, `standard`, `ha`) and the single-server installation stated
neither.

*The road to 1.0.0* names the restore drill S-03: an earlier version restored without Taktus,
checked by every tenant's chain verifying against a digest taken before, not by the database
starting. ADR-0087's tests restore a dump. Nothing restored to a chosen moment, and nothing ran
a drill on a schedule.

## Decision

### 1. Point-in-time recovery is an option of the chart's own database

`backup.pointInTime.enabled`, off by default. With it on, and only with `database.deploy: true`:

- the database runs from the **backup image**, which is the database's own image with
  `python3`, `age` and `rclone` added (ADR-0087 §1). Its server is the same;
- the server archives every finished segment through `archive_command`, which runs
  `taktus-backup archive-wal %p %f`. The program writes the segment to the backup's store under
  `wal/<system identifier>/<segment>`, encrypted to `backup.recipient` where one is set. A
  segment already in the store is not written again. The **system identifier** is the number
  PostgreSQL gives a database cluster when it is created, read with `pg_controldata`. A database
  restored from a dump is a new cluster with a new identifier, so it can never overwrite the
  segments an earlier cluster's base backups need. A database restored to a moment keeps its
  identifier and moves to a new **timeline**, whose segments carry another name;
- `archive_timeout`, `backup.pointInTime.archiveTimeoutSeconds` (300 by default), closes a
  segment after that many seconds even when it is not full, so that a quiet database is archived
  too;
- the database admits a replication connection from the backup's pod with the same password
  login. Its connection rules are the image's own plus that one line;
- each backup run takes a base backup beside the dump: `pg_basebackup` as one compressed tar
  stream that holds the segments it needs itself. It is named
  `taktus-<time>.base-<system identifier>-<first segment>.tar.gz`, so that the retention can read
  from the name which segments it needs, even when the manifest is encrypted. The manifest names
  it with its SHA-256 and size.

The dump stays. It is the restore a person does most easily, and it restores across a major
version of the server, which a base backup does not.

### 2. The retention keeps exactly the segments a kept base backup needs

After the backups older than the retention are deleted (ADR-0087 §4), the same run deletes every
segment of a cluster older than the first segment of that cluster's oldest kept base backup, and
every segment of a cluster no kept base backup names. The timeline's history files are never
deleted. With no base backup kept at all, no segment is deleted.

### 3. The drill restores into a scratch server in its own pod, and verifies every chain without Taktus

`taktus-backup drill` restores a backup into a server it creates in its own working directory —
the backup image is a database image — and never connects to the instance's database:

- **without a moment**, it restores the newest backup's dump, as ADR-0087 §5 does by hand;
- **with a moment** (`--to <time>`, or `--to latest`), it restores the newest base backup taken
  before that moment and replays the archived segments up to it. A moment the archive does not
  reach fails;
- the scratch server runs with archiving off and listens on no network address, so the drill
  never writes into the archive it reads, and nothing outside the pod reaches it;
- it then reads every tenant's ledger entries and **recomputes every chain by the ledger's
  published rule** (ADR-0006, ADR-0164, `src/taktus/components/ledger/__init__.py`): each entry's
  hash over its canonical form, each link to the entry before it in its chain, each place, and each
  anchor's tree over the run chains it covers. The program imports nothing of Taktus. A test holds
  its verdict to Taktus's own verification on the same entries;
- the **digest taken before** is the manifest's ledger heads, read before the dump (ADR-0087 §2):
  every head must be in the restored chain, with that hash. Given `--heads <file>`, the drill
  holds every tenant's newest entry to the file exactly, which is how a restore to a moment is
  checked against the heads noted at that moment;
- it measures the time from the first byte fetched until the chains are verified, the
  **machine's part** of the recovery time. With `TAKTUS_DRILL_RESTORE_SECONDS` set, a drill that
  took longer fails;
- it writes its report to the store as `drills/taktus-<time>.drill.json` — the backup, the
  moment, the seconds, every tenant's entries, head and verdict; never an entry's content — and
  keeps the drills by the backup's retention. Exit code 0 is a verified restore, 1 anything else.

The chart runs it as a CronJob, `backup.drill.enabled`, weekly by default. With
`backup.recipient` set, the drill must decrypt and needs the private key. The chart then requires
`backup.drill.identitySecret`. That puts the key into the cluster, which encryption was chosen to
keep out (ADR-0087 §3). The chart's documentation therefore says: with encryption, run the drill
off the instance, with the same image and the key from the operator's own store.

### 4. S-03 is the drill, and it is not a process bundle

S-03 of the blueprint `self-operation` is this drill. It runs from the chart's scheduler, not from
Taktus's. A drill that needs Taktus to run would prove nothing about repairing Taktus without
Taktus (ADR-0013 C). It is the same reason the backup is not a Taktus command (ADR-0087,
alternatives).

### 5. Each profile states its objectives

`deploy/k8s/README.md` §11 and the administration guide's page *Restoring* state the RPO and RTO
of each profile and of the single server. The RPO follows from the configuration: the backup's
schedule, or the archive timeout with point-in-time recovery. The RTO is a stated objective. Its
machine's part is measured by every drill and bounded by `backup.drill.restoreMinutes`. The time
a person needs to notice a failure and decide is not measured.

## Alternatives

- **A tool built for archiving PostgreSQL** (a dedicated backup and archive manager). It brings
  retention, parallel restore and compression. It is a second program to operate and to learn
  under pressure, and its restore needs it. `archive_command` with `rclone`, and
  `restore_command` with `rclone` and `age`, are lines a person can type.
- **Archiving by a sidecar container in the database's pod**, from a local archive directory. It
  keeps the store's credential out of the database's container. It needs a second volume, and a
  segment waits on the node until the sidecar ships it: the node's loss takes it along.
- **Only base backups, no dump.** Half the storage. A base backup restores only onto the same
  major version of the server, and the restore is less obvious than `pg_restore`.
- **The drill as a Taktus process**, with a worker that runs the restore. Rejected for §4's reason.
- **The drill's chain check through `taktusctl ledger verify`.** It is Taktus's own check, but it
  needs the control plane's image beside the restored server, and a Taktus whose verification is
  faulty would then confirm its own restore.
- **Recording the drill's outcome in the instance's database**, as the backup's (ADR-0106). The
  drill would then connect to the database it is meant to stay away from. Its report is in the
  store and its Job's state is the cluster's.

## Consequences

- `deploy/backup/backup.py` gains `archive-wal`, `fetch-wal` and `drill`, and the base backup
  in `backup`; `TAKTUS_BACKUP_POINT_IN_TIME`, `TAKTUS_CREDENTIAL_BACKUP_IDENTITY_FILE` and
  `TAKTUS_DRILL_RESTORE_SECONDS` are new settings. It still imports nothing of Taktus.
- The chart: `backup.pointInTime.*` changes the database's image, arguments and connection
  rules and mounts the store's credential into it; `backup.drill.*` renders a CronJob and its
  network policy.
- `CREDENTIALS.md`: the backup store's credential is also mounted into the database with
  point-in-time recovery, and the drill's private key is a parameter of its own.
- `tests/deploy/test_point_in_time.py` restores to a moment between two batches of entries;
  `tests/deploy/test_drill_chain.py` holds the drill's chain check to Taktus's.
- `deploy/backup/Dockerfile` takes `rclone` and `age` from their projects' releases, pinned by
  version and SHA-256 per platform: the distribution's builds carried fixed high and critical
  vulnerabilities, which the image scan of ADR-0173 (#347) refuses.
- No migration, no contract change, nothing in `src/`.

## Where this promise ends

Point-in-time recovery covers the chart's own database. For the `ha` profile's external
database, archiving and its restore are its operator's, and the chart neither sees nor checks
them; the drill restores the chart's dumps there. A segment is archived when it is closed: the
work of up to `archiveTimeoutSeconds` before a loss of the node is lost, and more if the store
was unreachable and segments waited on the database's volume. While the store is unreachable the
segments pile up on that volume and can fill it; the capacity watch sees the database's size, not
the cause. A moment before the oldest kept base backup cannot be restored. With `objectStore.kind: filesystem` the stored
files are archived once per backup: a restore to a later moment brings back rows naming files
that only the state volume holds, and that are lost with it. With point-in-time recovery the
database's pod runs from the backup image, so a release that changes that image restarts the
database. `fetch-wal` cannot tell a segment the store does not hold from a store it cannot reach:
a restore to `latest` while the store fails ends early, at the last segment fetched, and the
drill reports the newest entry it found rather than knowing what it missed. The drill restores the
newest backup by default: an older one is restored only on request. It verifies the ledger's
chains and the presence of the heads named before; it does not verify the provenance chains, the
object store's archive, or that a run resumes. The drill's time is the time of its own pod's
disk and processor, which may differ from those of the instance's restore. The drill with
encryption needs the private key wherever it runs. The RTO's part that is a person's — noticing,
deciding, typing the steps — is an objective and is not measured. The drill's report says that a
restore was possible on the day it ran, not that the next one will be.
