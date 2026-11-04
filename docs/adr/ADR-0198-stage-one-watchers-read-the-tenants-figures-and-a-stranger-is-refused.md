# ADR-0198 — Stage 1's watchers read the tenant's figures, and a stranger's request must be refused

**Status:** accepted · extends ADR-0192 (the processes of software-operations) and ADR-0109
(a signal judged against its corridor) · serves UC-03 B-1.02, B-1.03, B-1.07, B-1.08, B-2.03 ·
issue #437

## Context

Stage 1 of UC-03 adds watchers: people handle only deviations. Five of them were listed as not
built, each for a capability it seemed to lack.

- **B-1.02** names the costliest functions by their run times; **B-1.03** finds a function
  called far more than it should be, a loop or a retry storm.
- **B-1.07** tests the product's database rules against attack patterns: reading another
  account's data, counting up identifiers.
- **B-1.08** asks daily whether the backup ran, and monthly whether a restore into a test
  environment matched its samples.
- **B-2.03** compares the use of outside services' quotas with the quota.

Each figure is one a running software business already measures, if it measures at all. Run
times and call rates per function are what a metrics store holds. A backup job and a restore
drill report their last success as a metric; that is how their scheduler is watched. The quota
an outside service reports reaches the store through its exporter, where one exists. The
metrics connector reads any of them by the tenant's own query (`metrics.series`, ADR-0111).

A request for another account's record is a request a stranger makes. The check connector
already asks a path and judges the status (`check.http`, ADR-0111).

## Decision

### 1. A watcher of a figure is a query, a rule and a corridor

B-1.02, B-1.03, B-1.08 and B-2.03 each read the tenant's query through `metrics.series.query`
and select by the rule `filter` (ADR-0192 §1): the series with the highest value, a value the
store could not give as a number left out. A corridor of the tenant's judges it (ADR-0109). The
query is an input with a default, which the tenant replaces with its own store's names. No
figure is computed by a model; the selection is `exact`, with its check by recomputation
(DEC-0173).

B-1.08 judges two figures, two signals on two steps: the age of the last backup and the age of
the last restore drill. A drill that compared its samples and found a difference reports no
success, so its age grows until a person looks.

### 2. A stranger's request must be refused

B-1.07 asks two paths of the product as a stranger: a record another account owns, and the next
identifier after one the stranger may read. It uses the check connector with a second
credential, `CHECK_STRANGER_TOKEN`: the token of an account made only for the check, which owns
none of the records asked for. A check passes when the product refuses, with 401, 403 or 404.
A status 200 is a failed check. One failed check is red: a rule that lets a stranger read
another's data is an incident at once.

### 3. Each starts at level 1

Each only reads and judges; nothing leaves the system. At level 1 every step runs and none
acts (UC-03 §4). What each target level adds — proposing an optimisation, throttling a function,
renewing, changing a plan — is a capability not built here, named in the bundle's head.

## Alternatives

- **A connector per product: the cloud provider's function metrics, the backup tool's API, each
  outside service's quota endpoint.** Each would serve one tenant's choice. The metrics store
  is where a business that watches anything gathers these figures; one capability serves them
  all, and a tenant without a store has nothing a watcher could read either way.
- **The quota through the check connector, from rate limit headers.** An instance maps one
  connector to a capability. The check connector is the uptime check's, against one service,
  and could not ask the five services B-2.03 names.
- **B-1.07 as a model that writes attack requests.** The two patterns UC-03 names are fixed
  requests. A model would make them differ between runs and could not be held to a status.
- **The restore drill run by Taktus.** Restoring the business's database is an act on its
  systems with no generic interface. The drill is the business's job; Taktus watches that it
  ran and succeeded.

## Consequences

- Five bundles under `blueprints/software-operations/processes/`: B-1.02, B-1.03, B-1.07,
  B-1.08 and B-2.03, each rehearsed in `tests/composition/test_software_operations.py` against
  the fake metrics store and service, which gain the series and paths they read.
- `CREDENTIALS.md` describes `CHECK_STRANGER_TOKEN`.

## Where this promise ends

- **A watcher reads only what the tenant's store holds.** A business that exports no run times,
  no backup success and no quota has nothing these watchers read. Each fails at its read, and
  the failure reaches a person; it is never read as zero.
- **The query is the tenant's.** A query that measures something else is judged as given. The
  rehearsal proves the process over the fake store's series, not any tenant's query.
- **B-1.07 asks the two paths it is given.** It proves that those two requests are refused, not
  that the product's rules hold everywhere. An index deployment is not checked.
- **B-1.08 does not compare samples itself.** It trusts the drill job's report of success.
- **Nothing acts.** No optimisation is proposed, no function is throttled, no plan is changed;
  each stays with a person or with a capability that is not built.
