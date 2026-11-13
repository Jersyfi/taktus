# ADR-0310 — Flagged messages, a code search, a throttle and a weekly sum serve stage 1

**Status:** accepted · extends ADR-0111 (the mail connector), ADR-0151 (a statistics step),
ADR-0193 (the repository connector's operations), ADR-0198 (the watchers of stage 1), ADR-0201,
ADR-0204 and ADR-0211 (the serverless connector) · serves UC-03 B-1.02, B-1.03, B-1.12, B-2.04,
B-5.01 · issue #437

## Context

Five processes of stage 1 of UC-03 stopped short of their row, each for a missing interface.
The blueprint's README named every gap:

1. **B-5.01** lists open tasks *and flagged messages* by age. The mail capability read one
   message by its identifier and listed nothing.
2. **B-2.04** finds *retired model identifiers in the code*. No capability searched a
   repository's code; the tenant's version named the identifiers.
3. **B-1.03** *throttles* a runaway function in an emergency. No capability changed a
   function's limit.
4. **B-1.02** analyses *queries, egress and storage* besides run times, and *proposes an
   optimisation*. It read run times only and proposed nothing.
5. **B-1.12** reports *the pipeline's weekly cost*. No step summed a cost over a week.

Each has a published interface that serves it. IMAP searches a mailbox by the flag
`\Flagged` (RFC 3501 §6.4.4). The repository service has a code search,
`GET /search/code`. The serverless platform's service carries
`template.scaling.maxInstanceCount`. A metrics store answers a query for any series it holds.
A cloud's billing export answers each day's cost by service, which B-1.01 already reads.

## Decision

### 1. `mail.messages.flagged`

The mail connector lists the inbox's messages that carry `\Flagged`, oldest first. Each comes
with its identifier, subject, date and `days_old`: the whole days since its date. The input
`older_than_days` keeps those at least that old, and `limit` keeps the first ones. No sender and
no address is listed. One IMAP session is opened, and messages are fetched without being marked
read. B-5.01 runs a second flow from it when it is started without a task. A fixed rule orders
the list by age. A second fixed rule counts the messages a week old or more, for the tenant's
corridor. Nothing is written to anyone.

### 2. `repository.code.search`

The repository connector searches the default branch for a text through the service's code
search, `"<text>" repo:<owner>/<name>`. It answers each file's path and blob, sorted by path,
with the service's total. It reads at most ten pages of 100, the service's own limit of 1000.
`complete` says whether the service searched everything and every result was read. It is a new
capability, `repository.code`. B-2.04 searches for the first identifier it found retiring and
names the files in the issue it files.

### 3. `deployment.workloads.throttle`

The serverless connector sets a service's `template.scaling.maxInstanceCount` to
`max_instances`. The change makes a revision of the same containers, which takes the traffic.
The template carries the idempotency key as a release's does (`marked`). The output names the
limit before, so that a person can put it back. A service whose traffic is held on an earlier
revision, after a rollback, is a `conflict`: a revision from its template would roll it forward.

B-1.03 names a runaway by a fixed rule, a rate at or above the tenant's `throttle_above`, and
throttles its service to `throttle_to`. The tenant's query labels each series with the service's
name. The process starts at level 1: the throttle is proposed, and a person performs it. At
level 2 a person confirms it. At level 3, UC-03's target, Taktus acts on its own.

### 4. B-1.02 reads four drivers and proposes one change

B-1.02 runs three more of the tenant's queries on `metrics.series`: per database query, bytes
sent out, and bytes stored. A fixed rule takes the largest of each, as it takes the slowest
function. One issue names the four, with the goal the coding worker of P-03 is given: find one
change that lowers the largest of them. The issue carries the slowest function's mark and is
filed once while it is open. Filing leaves the system, so the process starts at level 2.

### 5. The statistic `total`, and B-1.12's week

A statistics step may compute `total`. It sums each group over every day of a series in decimal
arithmetic, largest first, with the series' total. A day whose total is not the sum of its
groups fails the step, as in `deviation`. B-1.12's weekly trigger gives `pipeline_group`. That
run reads seven days of `billing.costs` and sums them. A fixed rule keeps the group the pattern
names. Its amount is the figure for the corridor `pipeline.weekly_cost`.

## Alternatives

- **A flag read per message.** A run per message would need the identifiers first, which only a
  listing gives.
- **A clone and a search in a sandbox for B-2.04.** It reads the whole repository for one text
  the service already indexes.
- **Scale to a number of instances.** The platform scales itself; what bounds a runaway is the
  ceiling, not the number running.
- **Egress and storage from the billing export.** The export groups by service, and egress and
  storage are kinds of usage within a service. The metrics store holds them by sender and by
  store, which is what a change can act on.
- **A rule that sums.** The rules select and match; arithmetic over a series is what the
  statistics step is for (ADR-0151).

## Consequences

- `mail.messages.flagged` on the mail connector; `repository.code.search` and the capability
  `repository.code` on the repository connector; `deployment.workloads.throttle` on the
  serverless connector. All are in `composition/shipped.json`.
- The statistic `total` beside `deviation`.
- B-5.01 version 3, B-2.04 version 3, B-1.03 version 3, B-1.02 version 3 (named *Cost drivers*,
  at level 2), B-1.12 version 4.

## Where this promise ends

- **A flag has no date.** IMAP keeps no moment at which a flag was set. A message's age is its
  own date's, and a message flagged today that was written a month ago counts as a month old.
- **Flagged messages on a mail service's API are not listed.** The `resend` connector serves
  `mail.messages` without flags; B-5.01's second flow runs on the IMAP connector only.
- **The code search finds what the service indexed.** It searches the default branch only. A
  file too large or too new for the service's index is not found. One identifier is searched per
  run, and the coding worker that makes the switch searches the rest.
- **The identifiers in use stay the tenant's list.** The search finds where a known identifier
  occurs. It does not find which identifiers the code uses.
- **The throttle is served by the serverless connector only.** The cluster connector serves
  `deployment.workloads.scale`, a number of replicas, and no ceiling. A function on a hosted
  functions service behind `deployment.sites` is not throttled.
- **Raising the ceiling again stays with a person.** Nothing restores the limit before, and a
  limit changed for good is a person's at every level (UC-03 §4.1).
- **The cost drivers are the store's units.** Seconds and bytes are compared within a driver,
  never across drivers or into money. Their price is the bill B-1.01 reads.
- **The pipeline's cost is what the cloud bills.** The minutes of the repository service's own
  runners are billed to its account outside any cloud's export, and are not read.
