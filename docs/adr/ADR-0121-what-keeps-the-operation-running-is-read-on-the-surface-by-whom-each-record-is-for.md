# ADR-0121 — What keeps the operation running is read on the surface, by whom each record is for

**Status:** accepted · builds issue #562 on DEC-0218 · extends ADR-0063 (the web app), ADR-0106 (alerts), ADR-0107 (incidents) and ADR-0109 (signals)

## Context

DEC-0218 says the web app is where everything Taktus knows is found. Four kinds of record say
whether the work runs as it should:

- an **incident**, raised by rule when an expected run did not happen or did not end in time,
  when a signal turned red, or when a level fell (ADR-0107, ADR-0109 §4, ADR-0110);
- an **alert**, a condition that needs a person's action, reported to the owner (ADR-0106);
- the **backup's** recorded outcome, and the interval a success is expected within (ADR-0106 §3,
  §5);
- a **signal**, judged against its corridor, and the daily report of what deviates (ADR-0109).

Each was readable only through `taktusctl` or the owner's channel. The HTTP surface had no route
for any of them, so the web app could show none.

Two readers stand apart. Every reader of a tenant sees its runs and processes, through one
predicate (ADR-0055 §5). The reports to the owner are read by the owner and the people the owner
named, and nobody else (ADR-0045).

## Decision

### 1. One read route per kind, and one for the start page

| Route | Answers |
|---|---|
| `GET /operation` | one entry per kind, for the start page: incidents open, alerts in effect, the backup's standing, signals red, yellow and not measured, the newest daily report |
| `GET /incidents` | every incident, open and closed, newest first |
| `GET /alerts` | every alert, with what became of its report |
| `GET /backup` | the last success, the failed runs since, by when the next success is due |
| `GET /signals` | every signal in force, judged now, beside its corridor |
| `GET /signals/daily-report` | the newest report of kind `signals`, as its view |

Each route reads the account key from `Authorization: Bearer` and nowhere else, as the rest of
the surface does. Each answers `401` without a key. No route writes.

### 2. Who reads what follows what the record is about

- An **incident** and a **signal** are about a process. A reader sees one where the one
  predicate lets them see that process (`visibility.may_see_process`). A record whose process is
  withheld is absent and not counted.
- An **alert**, the **backup** and the **daily report** are reports to the owner. The owner and
  the people the owner named read them (`ReportQueries.may_read`). Anyone else is answered `403`.
- `GET /operation` gives each reader a figure only for what they may read. A kind they may not
  read carries `readable: false` and no figure.

### 3. Each record names what a reader can open

An incident names its process version, its run where it has one, and the runs its timeline
records. A signal names its process, the run and the step that measured its newest value, and
its case. An alert gains `about`: the runs, steps and process versions its facts name. An alert
about the whole instance, such as capacity or the backup, names none.

The backup's next success is due by the last success plus the expected interval. Without a
recorded success, the tenant's creation counts, as the alert's rule counts it
(`alerts.backup_due`).

### 4. Nothing new is computed for the surface

Each read asks the component that owns the record, through the composition root
(`composition/operation.py`). The incidents are the governance component's; the alerts, the
backup and the signals are the reporting component's, read by the same rules the scheduler
reports by. The surface shapes each record into a document and adds nothing to it.

### 5. No record names a person

An incident's closing person is the actor of its ledger entry, and is not shown. A corridor
names the operation, a role or a department. The daily report's view says whether its reader
acted, never who did (ADR-0045).

## Alternatives

- **Every reader reads every kind.** An alert and the daily report are reports to the owner;
  reading them wider than their own route `GET /owner/reports` would make one route wider than
  another.
- **Only the owner reads every kind.** A reader who sees a process's runs would then not see
  that its expected run did not happen. The incident is about the process, as the run is.
- **The start page asks each route.** A reader who may not read the alerts would be answered
  `403` on every visit to the start page. One summary says so once.

## Consequences

- `adapters/driving/rest/operation.py`: the six routes; `wiring.py`: `OperationReads`.
- `composition/operation.py`: `OperationRecords`, and `Wired.operation`.
- `reporting`: `AlertRef` and `Alert.about`; `alerts.backup_due`; `Alerts.backup` and
  `BackupWatched`.
- The web app's pages `#/incidents`, `#/alerts`, `#/backup` and `#/signals`, and a section on
  the start page.
- `api/openapi.yaml` and the web app's fixtures, regenerated.

## Where this promise ends

A record is as fresh as its source. The alerts and the signals are computed when they are read.
The incidents are what the watch raised at its last look, once a minute while a scheduler leads.
The backup is known only from what the backup program recorded. A page is read once on opening
and does not follow the stream of changes; a reader reloads it. Until the role-based views of
UC-6.4, the predicate is the tenant boundary, so every reader of a tenant sees all its incidents
and signals. Whom the owner named is the owner's channel's configuration; a tenant without one
has nobody who reads the alerts, the backup or the daily report on the surface. An incident is
closed and a corridor changed only on the command line; the web app shows them and changes
nothing.
