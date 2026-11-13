# ADR-0295 — The instance's health, the backup's listing and a tenant's export are administrative acts in both ways in

**Status:** accepted · extends ADR-0279 (the inventory of administrative acts), ADR-0221 (a
tenant's export and import), ADR-0106 (the backup's outcomes), ADR-0093 (readiness) · UC-10.2

## Context

UC-10.2 asks that every administrative act is available through the command line and through
the web app, and that a backup can be listed and its age seen by an administrator. ADR-0279 built
the inventory of administrative acts and left four out: a tenant's export and import, the
backup's listing on the command line, and the instance's health. The export and the import
existed on the command line and the HTTP surface (ADR-0221), but the web app had no form for
them. The backup's standing was a page of the web app (ADR-0121), with no listing of its runs and
no command. The instance's health was `/health` and `/ready`: answers for a platform's probes,
not a page or a command for a person.

## Decision

### 1. Five more acts in the inventory

`adapters/driving/inventory.py` names `tenant.export`, `tenant.import`, `backup.list`,
`instance.health` and `instance.update` (ADR-0296), each with its command, its operation and
its page. `tests/adapters/test_administration_inventory.py` finds each in both ways in, as it
does every other act.

### 2. A tenant's export and import in the web app

The page `#/tenants` exports each tenant to one file and imports a file, with the instance's
administration key, by the operations ADR-0221 made. After an import the page says what was
written and what each check of the chains found. A failed check is said, never hidden.

### 3. The backup lists its newest runs

The backup's port answers the newest runs of the tenant as well — at most thirty, succeeded or
failed, newest first — besides the last success and the failures since. `GET /backup` carries
them as `listed`. `taktusctl backup list` prints each with its name, when it ran and how long
ago, and by when the next success is due. The page `#/backup` lists them with their age, which
it computes from the time each run recorded and the reader's clock.

### 4. The instance's health, for a person

`GET /administration/health` answers the release this process runs, whether it may receive
traffic and why not, the roles it serves and whether it leads, and for the reader's tenant how
the backup stands, how many alerts are in effect and how many incidents are open. It needs a
role holding `tenant.administer`, as every act of `/administration` does (ADR-0279 §2).
`taktusctl health` prints the same from the state it opened. The page `#/health` shows it and
leads to the backup, the alerts and the incidents. `/health` and `/ready` stay as they are, for
the platform.

### 5. Restoring stays a person's act

Neither way in offers a restore. A restore counts as potentially destructive (`CLAUDE.md` §9),
and the guide *Restoring* carries it out without Taktus (ADR-0013 C). Both ways in say so where
the backup is listed.

## Alternatives

- **The listing read from the backup store.** The store is the backup program's, which imports
  nothing of Taktus and holds the credentials to it (ADR-0013 C). The outcomes the program records
  in the database are what the instance knows; the listing reads those.
- **Health as an extension of `/ready`.** `/ready` is answered without a key, for the platform;
  the tenant's backup, alerts and incidents are the tenant's and need a reader.

## Consequences

- `ports/backups.py`: `BackupHistory.recent`; both backup log adapters fill it.
- `reporting`: `BackupRun.outcome`, `BackupState.recent`, `BackupWatched.standing`.
- `rest/administration.py`: `/administration/health`; `rest/operation.py`: `listed`.
- `cli/instance_command.py`: `health`, `backup list`.
- `web/src/routes/health`, `HealthView.svelte`, the listing in `BackupView.svelte`, export and
  import in `TenantsView.svelte` and `governance.ts`.

## Where this promise ends

- The listing shows what the backup program recorded. A recorded success does not say that the
  backup restores; the restore drill shows that (ADR-0222).
- The listing holds the newest thirty runs. An older run is in the backup store, which the
  backup program lists, not Taktus.
- The release the health shows is the installed package's version. A build from a checkout
  without a release tag shows the version its package states.
- The health's readiness is this process's. Another process of the same instance may answer
  otherwise; the platform's probes ask each one.
