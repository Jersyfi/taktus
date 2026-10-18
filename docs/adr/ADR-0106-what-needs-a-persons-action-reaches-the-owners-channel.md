# ADR-0106 — What needs a person's action reaches the owner's channel

**Status:** accepted · builds issue #323 and the third requirement of #322 on ADR-0045 and
ADR-0047 · amends ADR-0087

## Context
`docs/architecture/platform.md` promises that Taktus tells a person when they must act. Three
signals reached only the log and the ledger (DevOps review §K5, DEC-0187):

- a **capacity finding that turns to *act***: storage or memory is running out
  (`capacity.<resource>`, platform.md §3);
- a **runner that lost its claim** on a run: it could not reach the database, or was paused, for
  longer than the lease, and another runner took the run over (`runner.py`). Nothing recorded it
  beyond the runner's own outcome in memory;
- a **failed or missing backup**. The backup is a CronJob that imports nothing of Taktus
  (ADR-0013 C, ADR-0087). The instance did not know whether a backup ran.

ADR-0047 already reports a broken interface this way. A rule over recorded facts finds what is
open. The scheduler raises a report of kind `failure` through the owner-facing channel
(ADR-0045), idempotent by the report's identifier, and tries an undelivered message again once
an hour. A tenant without a channel raises nothing, and the view says so.

Three questions were open. What does the instance learn a backup from? Where is that fact kept,
given that every row carries its tenant (ADR-0020)? And whose channel hears of a fact about the
whole instance?

## Decision

### 1. The same mechanism, three more rules
The reporting component gains the use case `Alerts` (`reporting/application/service/alerts.py`).
It reads recorded facts through its port `Signals` and applies one rule per signal
(`reporting/domain/service/alerts.py`). Each open alert raises one report of kind `failure`
through `RaiseReportHandler`, as ADR-0047 §4 does. The report states what happened, what to do,
what stands still, and today as its date. Its identifier is derived from the facts and never
stored, so it is raised once. While the scheduler leads, it looks once a minute
(`composition/alerts.py`). A message that was not delivered is tried again once an hour, while
the alert is still in effect.

An alert ends in one of two ways. It **clears** when the facts say the condition is over. It is
**closed** when the owner answered its report that it is done (ADR-0045 §5). A cleared or closed
alert sends nothing more. The same condition arising again later is a new alert, with a report of
its own.

| Alert | Identifier from | Open while | Clears when |
|---|---|---|---|
| capacity | the `capacity.<resource>` entry with outcome `act` | it is the newest entry of its kind | an entry of the kind with outcome `ok` follows |
| claim lost | the first `run.claim_lost` entry since the last alert of this kind closed | not answered done | never on its own: each loss is an event |
| backup | the name of the last successful backup, or `never` | the newest outcome failed, or the last success is older than the expected interval | a successful backup is recorded within the interval |

Nothing else decides. No model, no estimate and no reading of words is involved (ADR-0023, as
ADR-0047 §3 holds it).

### 2. A lost claim is a ledger entry of the run
When a runner learns that it lost its claim — a write refused by the fence, or a heartbeat that
could not renew — the engine records `run.claim_lost` in the run's chain, with outcome `lost`.
The entry names the run, its plan and its process version, and nothing else. It names no
runner, no host and no person. It is written outside the claim. The run is another runner's
now, and the entry changes nothing of it. A recording that fails is logged by the runner and
does not stop it.

### 3. The backup records its outcome in the database it backs up
Migration 0055 creates the table `backup_outcome`. A row holds a tenant, a time, the backup's
name, `ok` or `failed`, and for a failure the step that failed as a token: `configuration`,
`database`, `encryption`, `objects`, `store` or `retention`. A token is never a message, so no
secret and no tool output can reach the row.

At the end of every run, `backup.py` inserts one row per tenant of the table `tenant`, through
`psql`, with the login it backs up with. That login reads every row already (ADR-0087 §2). The
program still imports nothing of Taktus. A recording that fails is printed and changes neither
the backup nor the exit code. A run that cannot reach the database records nothing, and that is
then seen as a missing backup.

The table follows ADR-0020. It carries `tenant`, and row-level security keeps each tenant's
rows apart. The application role may only read it. The only table without the column is
`tenant` itself, which is the registry of tenants. The scheduler's election is an advisory lock,
not a table. An instance-level table would have been the first of its kind. One row per tenant
needs no exception, and each tenant reads its own rows under its own setting.

### 4. Every tenant whose data the fact concerns hears of it
A capacity crossing is already recorded in the chain of every tenant the instance serves,
because every tenant's work stands on the same platform (platform.md §3). A backup holds every
tenant's data, so its outcome is a row of every tenant. Each tenant's owner-facing channel
therefore hears of both. A lost claim concerns one run, and its tenant hears of it. The
instance's administrator has no channel of their own. The administrator is whoever can run the
command line against the database, or holds the administration key, and neither names an
address (ADR-0104 §4).

### 5. The expected interval is configuration
`TAKTUS_BACKUP_EXPECTED_HOURS` says how old the last successful backup may be. Unset, a missing
backup is not watched, and a recorded failure still is. The chart sets it from
`backup.expectedHours`, 26 by default, whenever `backup.enabled` is true. The schedule is daily,
and two more hours absorb a run that starts late or takes long. A tenant with no recorded backup
counts from its own creation.

### 6. Without a channel, today's behaviour, said at startup
A tenant without an owner-facing channel raises no report. Its findings stay in the log and the
ledger, as before. When the daemon starts, it logs one line for every served tenant without a
channel, and one line saying whether backups are watched. `taktusctl alerts` shows every alert,
with what became of its report: delivered, not delivered with the reason, cleared or closed.

## Alternatives
- **The backup writes a ledger entry.** It would have to extend each tenant's hash chain with
  `psql`, outside the ledger component. A second writer of the chain's rules is a defect waiting
  to happen (ADR-0006).
- **The daemon reads the backup store.** It would need the store's credential, which may delete
  (DEC-0058). It would also need `rclone` or an S3 client in the control plane's image.
- **The cluster's CronJob status.** The daemon would need to read the cluster's API, which the
  core must not call directly (CLAUDE.md §6), and an instance outside a cluster would have none.
- **One instance-level row per backup, without `tenant`.** It would be the first table of its
  kind and an exception to ADR-0020 §4. Every tenant would then read rows outside row-level
  security.
- **A report for every lost claim.** A database outage of a minute loses every claim at once,
  and the owner would receive one message per run. One alert holds them all until it is
  answered.
- **Clearing a capacity alert by an answer only.** The ledger already says when it cleared. A
  cleared condition that keeps sending would teach the owner to ignore the channel.

## Consequences
- `reporting`: `CapacityCrossing`, `ClaimLost`, `BackupRun`, `BackupState`, `Signalled`,
  `Alert`; the rule and its words; the port `Signals`; the use case `Alerts`.
- `run`: the ledger kind `run.claim_lost`, written by `RunEngine.record_claim_lost`, which the
  runner calls.
- `ports/backups.py`, `BackupLog`; the adapters `PostgresBackupLog` and `MemoryBackupLog`.
- Migration 0055, the table `backup_outcome`.
- `deploy/backup/backup.py` records every run's outcome. The chart sets
  `TAKTUS_BACKUP_EXPECTED_HOURS`.
- `composition/alerts.py`, the scheduler's look, the startup lines, and `taktusctl alerts`.

## Where this promise ends
An alert reaches a person only where the tenant configured an owner-facing channel and its
connector delivers. Otherwise it is in the log, the ledger and `taktusctl alerts`, and nowhere
else. The scheduler looks once a minute while it leads. With no scheduler running, nothing is
said. A capacity alert is as fresh as the capacity report, made every
`TAKTUS_CAPACITY_INTERVAL_SECONDS`. A CPU finding is never recorded, so it is never reported.

A lost claim is noticed only by the runner that lost it, and only once it can write again. A
runner that dies is not a lost claim: its run is recovered (`run.recovered`), and that is not
reported. A claim-lost alert says how many runs lost their claim and names the first ones. It
does not say why the runner lost them.

A backup is known only from what it recorded in the database. A run that cannot reach the
database, or that runs against a database without the table, records nothing. It is reported
only once the expected interval has passed. A missing backup is not watched where
`TAKTUS_BACKUP_EXPECTED_HOURS` is unset. A tenant created since the last backup has no row of
it, and is reported once its own creation lies further back than the interval. A recorded `ok`
says the program wrote the backup and saw it listed in the store. It does not say that the
backup restores: that is the drill of S-03. A row is written with the backup's own clock. A
restore brings back the outcomes as they were at the dump, and the restored instance reports a
missing backup until the next one records. The table is never pruned: it gains one row per tenant
per run. An instance upgraded to this release reports a missing backup once, until the first
backup of the new image records, if its tenants are older than the interval.
