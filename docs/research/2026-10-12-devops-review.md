# A DevOps review of the concept, with measurements — 2026-10-12

**Why this file exists.** The owner asked for a critical review of whether Taktus's concept holds
for production use: across the whole range of customers, with resources used sensibly. Every
finding below was proved or refuted by an experiment against the real code. The owner adopted
every finding (DEC-0187). The issues that carry them name this file as their source. This file is
the evidence behind them.

**How it was made.** A session wrote one script per finding. Each script ran against commit
`6aa82a7` and a private PostgreSQL 16 in Docker Desktop on macOS, with 14 cores. The scripts then
ran a second time, one after another, so that no other load distorted them. Absolute figures are
indicative; the ratios hold. The scripts stayed outside the repository. Each finding says enough
to rebuild its experiment. Where a figure comes from a prototype of the remedy, the prototype gave
the same stored or computed result as the shipped code.

**The customer range it was read against** (DEC-0188):

- a person or a family: one tenant, one machine;
- a small business: one tenant with a few departments;
- a corporation: one tenant with many departments, whose processes cross the department boundaries;
- an operator: one instance that hosts many tenants for others, B2C or B2B.

**It expires.** It describes the code of one date. Each issue states its own verification
condition, so the issue does not depend on this file staying true.

---

## Correctness and stability

**D1 — a deadlock between two locks (#309).**
- *What happens.* `ChainedLedger.record` holds an `asyncio.Lock` shared by the whole process. Meanwhile `PostgresLedgerStore.last` takes `pg_advisory_xact_lock` for the tenant, which is held until commit. A commit that records two entries waits for the process lock a second time while still holding the tenant's lock. A second transaction of the same tenant meanwhile holds the process lock and waits for the tenant's lock.
- *Measured.* Through `RunEngine.start` with a trigger, 2 or 4 runs of one tenant hung in 6 of 6 trials, and 0 of 9 without a trigger. In a free race, 4 transactions recording two entries each hung in 10 of 10 trials, and those recording one entry each in 0 of 10. `pg_stat_activity` showed one session `idle in transaction` holding the lock and one waiting on `advisory`.
- *Consequence.* No timeout ends the hang, and the lease heartbeat keeps the job claimed. With two tenants in one process there was no deadlock, but the second tenant's write took 2.9 s instead of 0.013 s.

**E4 — listing runs (#310).** `RunMapper.list` filters every child row once per run in Python, and `GET /runs` has no pagination.

| Runs | Query alone | `GET /runs` | Event loop blocked | One-pass grouping |
|---|---|---|---|---|
| 100 | 0.08 s | 0.56 s | 0.4 s | 0.18 s |
| 1 000 | 0.15 s | 11.8 s | 11.5 s | 0.6 s |
| 2 000 | 0.33 s | 56.9 s | 56.0 s | 1.1 s |

The overview answers 254 bytes and still loads every run. With `TAKTUS_ROLES=all`, API and runner
share one event loop, and the lease is 60 s.

**M1 — the object store's cache (#311).** `MemoryObjectStore` keeps every object it wrote or read in
a dict that is never evicted. With 2 000 objects of 512 KiB, the process grew from 47 MiB to
1 082 MiB. After a restart, reading the same objects again took it to 1 639 MiB. The chart limits
the roles to between 384 and 768 MiB.

**G1 — cache writes (#312).** The model adapter's `_by_kind` reads only
`prompt_tokens_details.cache_write_tokens`. When 8 000 writes are reported as
`cache_creation_input_tokens` at the top level, they are booked as 10 000 tokens of input and no
cache write. The same writes reported in the nested field are booked correctly. The gateway's
documentation names the top-level shape (`docs/research/2026-10-12-market-review.md`). This was not
yet checked against a real endpoint. The adapter also ignores `Retry-After` on a `429`.

**X1 — the project inside the product (#313).**
- *What leaks.* `run/domain/service/budget.py` ships `SEED`: the eight P-03 runs of 2026-09-23, so every install calibrates its budgets from the Taktus project's coding worker. Besides that, the guides manifest defaults to this repository's layout. The chart sets `model.outputCap: hard`, a value measured against the project's endpoint. The findings take the shape of this repository's issue form. Error and help texts name project processes.
- *What is clean.* No blueprint ships in the image. No project process is scheduled by default. The product's decision register lives in the database.

## Many tenants, one tenant with many departments

**T1 — what a tenant costs while idle (#318, #350).**
- *Where the tenant list lives.* An instance reads its tenants once from `TAKTUS_TENANTS`, and no command creates a tenant.
- *How tenants are served.* Runners, triggers, reactions and the capacity report visit the tenants one after another, with at least one transaction per tenant per round.
- *Ceiling.* One environment variable of 128 KiB caps an instance at about 3 500 tenant identifiers shaped like UUIDs. Starting with 3 600 failed: "argument list too long".

An idle `taktusd` running every role:

| Tenants | Commits/s | CPU of one core | Runner round |
|---|---|---|---|
| 1 | 4 | 1 % | — |
| 100 | 308 | 19 % | — |
| 1 000 | 243 | 30 % | — |
| 10 000 | 564 | 48 % | 24.9 s against a 1 s poll |

The interface sweep every 60 s read the whole ledger of every tenant with a configured channel. It
took 9.5 s for 1 000 tenants with 200 entries each.

**T2 — colliding lock keys (#317).**
- *Key space.* The ledger's lock key is `hashtext('taktus.ledger:<tenant>')`, 32 bits wide. The scheduler's leadership lock uses the same key space.
- *Probability of a collision:* 0.012 % at 1 000 tenants, 1.16 % at 10 000, 25 % at 50 000 and 69 % at 100 000.
- *A colliding pair found:* `tnt_111599` and `tnt_85816`. A write of one waited 1.99 s on the other, against 0.012 s for a control tenant. In one process the D1 deadlock then struck the two different tenants.
- *A collision with the leadership key:* the tenant id `acme-5a1311c5` was found in 62 s on one core. That tenant cannot write while the leader lives.

**T3 — fairness (#319, #343).**
- *Nothing below the tenant is scoped.* `org_path` exists only on identities and commands, and the queue is first in, first out per tenant. When department A queued 200 runs, department B's one run waited 50.6 s.
- *Tenants are served in list order.* With tenant A holding 1 000 queued runs, tenant B waited 252.9 s with `TAKTUS_TENANTS=A,B` and 0.14 s with `B,A`.
- *Runner throughput.* A runner whose places are all taken sleeps a full poll, which caps it at about four runs per second.

**L1 — one write queue per tenant (#341).**
- *Why.* Every commit holds the tenant's chain lock until it ends.
- *Measured.* With 2 ms of work in each transaction, one tenant tops out at about 200 commits/s however many writers there are: 142 with 1 writer, 199 with 2, 220 with 4, 205 with 8. With one tenant per writer it reached 119, 348, 583 and 1 020.
- *Translation.* A step takes about three commits, so this ceiling is about 60–70 steps per second for a whole corporation in one tenant.
- *Why splitting is no way out.* A corporation's processes cross its departments, so dividing its tenant does not lift the ceiling.

## Long-lived growth and waiting

**L2 — whole-ledger reads (#321).** These read a tenant's whole ledger:
- the calibration at every run start, resume and claim;
- `GET /runs/{id}/ledger`, which also verifies the whole chain;
- `BlockedTime`;
- the interface sweep;
- the reads for cost, Takt and registration.

The index `ledger_entry_run` is never used.

| Entries | Run start | `GET` a run's ledger | Peak memory | Projection / index |
|---|---|---|---|---|
| 10 000 | 0.13 s | 0.31 s | 183 MB | 31 ms / 5 ms |
| 100 000 | 1.5 s | 3.6 s | 607 MB | 16 ms / 15 ms |
| 500 000 | 23.6 s | 26.2 s | 2.5 GB | 9 ms / 63 ms |

The projection keeps the last twenty observation pairs per adapter and method, which is all the
calibration uses. At 500 000 entries it gave exactly the factors computed from all 83 433
observations.

**E1 — waiting inside a runner's place (#320).**
- *What happens.* A `wait` step sleeps inside the step, and `wait-for-pipeline` polls inside it for up to 30 minutes. Each holds a place and its lease the whole time.
- *Measured.* Four places, five runs each waiting 5 s: 10.2 s in total, and a short run waited 4.67 s. With the wait parked as a deferred job: 5.3 s, and the short run waited 0.08 s.
- *For comparison.* A wait for a person frees the place already: 0.6 s in total.

**E3 — the whole run rewritten on every commit (#325).** Every commit deletes and re-inserts every
step run, checkpoint and artifact of the run.

| Steps | Rows deleted | Run time today | Upsert of the changed step |
|---|---|---|---|
| 50 | 7 650 | 3.0 s | 1.3 s |
| 100 | 30 300 | 20.9 s | 2.3 s |
| 200 | 120 600 | 61.5 s | 5.3 s |

## Execution and installation

**E2 — a unit for every estimate (#324).**
- *What happens.* A launched worker starts a probe unit for every estimate, and then the unit for the assignment.
- *Measured, per worker step.* Two starts with every adapter. With the container adapter, 2.28 s of starting and stopping against 0.33 s of work; every launch created a network, an egress container and a unit container. Against a fake of the cluster's API: 3 jobs, 3 services, 1 secret and 29 API calls. A bare container start of the same image to its health answer took 0.41 s.

**K6 — the smallest install (#326).**
- *One process.* With every role, it idles at 145 MB and 1 % CPU, with 6 database connections and ready after 1 s.
- *The chart's minimal install.* 4 role deployments plus the database: 5 pods, 0.5 core and 1 280 MiB requested, 3 072 MiB of limits, 25 GiB of volumes.

**K1 — one node (#342).** `helm template` shows the following:
- every role mounts the one `ReadWriteOnce` claim `taktus-state`;
- the database's StatefulSet has one replica on a node-local 20 GiB volume that cannot be expanded;
- there is no PodDisruptionBudget, autoscaler, affinity or topology spread.

With two replicas each of api and runner, six pods share one ReadWriteOnce claim.

**K2 — the restore (#322, #346).**
- *Setup.* A real run of the example process with the reference worker, then `pg_dump -Fc` as `backup.py` takes it, restored into a fresh database with an empty state directory.
- *Finished run.* 0 of 20 referenced digests were readable after the restore, against 20 of 20 with the original volume.
- *Halted run.* Resumed after the restore, it escalated: an artifact's content was not available. `taktusctl cost` gave a misleading reason.
- *Not covered.* The backup holds the dump and its manifest only. There is no point-in-time recovery and no alert on a failed backup.

**K3 — upgrades (#330).**
- *Why it breaks.* Readiness requires the database's schema revision to equal the build's head exactly. The migration runs as a pre-upgrade hook.
- *Timeline.* The old process's `/ready` went from 200 to 503 about 0.1 s after the migration, and the new one was ready about 2 s later. In a cluster, image pull and probe time widen that gap.
- *Old build against the new schema.* The old build (`e5be9cc`, needing 0027) refuses the new schema (0049) and exits with code 3. Yet 0049 only adds a nullable column.
- *The way back.* `alembic downgrade 0027`, run with the new image, made the old build ready. No runbook describes that.

**K5 — who learns that something needs action (#323, #347).**
- A capacity finding of *act* goes only to the log and the ledger (`composition/capacity.py`).
- There is no metrics endpoint, no alert rule and no dashboard.
- Images are built only on tags, with no scan and no signature.

**K4 — documents that no longer matched the code.** Corrected in the pull request that records
this review (DEC-0191).

## The project's own process

**P7 — ceremony and control (#314, #315, #316).**
- *What was analysed.* 122 squash-merged pull requests, 888 CI runs and the whole register.
- *Confirmed.*
  - The register is 13 % of all changed lines.
  - Process gates stopped 41 of 132 branches; product gates stopped 14.
  - 47 of 76 failures of the description check were a stale copy of `make status`.
  - 24 of 53 requests were written after the owner had answered.
  - The owner granted widenings of the session's authority 10 times out of 10.
  - Use-case requirement requests followed the recommendation 9 times out of 9.
  - No notice was overridden, 0 of 106.
- *Refuted.*
  - The owner is not a bottleneck: the median answer came after 1 day, the longest after 8.
  - 81 % of pull requests ship product.
  - Process gates cost 1.5 % of CI time.

The six rules the owner adopted are DEC-0189.
