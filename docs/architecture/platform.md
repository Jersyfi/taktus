# The platform an instance runs on

Taktus runs a business's processes on some machine. That machine has a fixed amount of memory,
processor time and disk. When one of them runs out, work stops. When it stops without warning,
nobody knows until somebody asks why nothing happened.

**Taktus keeps an eye on the platform it runs on, and tells a person when they must act — so
that work never silently stops.** It does so in three stages:

| Stage | What Taktus does | Version | State |
|---|---|---|---|
| **Observe** | measures what is left and how fast it is used; reports a figure and a date before it is tight; refuses a job that would not fit | `0.1.0` | **built** — §1 to §5 |
| **Propose** | says what more capacity would buy, and what it would cost | `0.5.0` | specification — §6 |
| **Manage** | acts on the platform within a budget, where the environment permits | `0.7.0` | specification — §7 |

Two facts about the first target make this urgent rather than tidy. The machine has **no swap**.
Swap is disk space the kernel uses as memory when memory is full; without it, a process that
needs more memory than is left is killed by the kernel at once, without a message to anyone. And
the database's volume is created at 20 GiB on a storage class that **cannot enlarge a volume
after it was created**, while the ledger only grows. A full volume there is a migration, and a
migration takes days to plan.

---

## 1. What is observed

The platform port (`src/taktus/ports/platform.py`) answers one question: what is left, now. It
reports three quantities, each as *free* of *total*:

| Quantity | Unit | Means |
|---|---|---|
| CPU | cores | the cores this instance may use, and how many of them are idle |
| memory | bytes | the memory this instance may use, and how much of it can still be allocated |
| storage | bytes | the filesystem the state directory lives on, and what an unprivileged writer may still use; beside it, how many bytes the state directory holds |

**A value the adapter cannot observe is `Unobserved`, with the reason.** It is never a guess. An
observed value names its *source* — the file or call it came from — so that a reader can tell a
measured figure from a derived one.

The adapter for the machine or container the instance runs on is
`src/taktus/adapters/driven/platform/host.py`. It uses the standard library only:

- **Memory.** Inside a container, the kernel enforces the container's limit, so the adapter
  reads the container's *control group* first. A control group is the kernel's accounting
  unit for a group of processes; a container is one. Version 2 (`memory.max`,
  `memory.current`) is read first, then version 1. The page cache the kernel would give back
  first (`inactive_file`) is not counted as used. Without a control-group limit, the machine's
  own figure follows: `MemAvailable` of `/proc/meminfo`. Where both answer, the smaller free
  figure wins. On macOS the total is known and the free amount is not, so memory is
  `Unobserved` there with that reason.
- **CPU.** The cores this process may run on, capped by a control-group quota where one is set.
  Under a quota, the idle share is measured over a sample of a quarter second. Without one, the
  one-minute load average stands for what is busy.
- **Storage.** `shutil.disk_usage` on the state directory, or on the nearest existing directory
  above it. The bytes the directory holds are found by walking it.

**The database is not the platform's.** Its volume is usually not visible from the instance. Its
size comes from the persistence port instead (`StateSize` in `ports/persistence.py`): the
database adapter reports the size the server gives for the database, and the development store
reports its snapshot files. The size of the volume under the database is *told*, as
`TAKTUS_CAPACITY_DATABASE_VOLUME_MB`. Untold, the database's free space is `Unobserved`, and the
report says so.

## 2. How growth is measured

A date needs a rate. The rate here is **growth per run** times **runs per day**.

- **Runs** are counted from the ledger: every `run.created` of the tenants the instance serves.
  The ledger store counts them without reading the chain (`LedgerStore.summary`), so the report
  costs the same on the first day and in the fifth year.
- **Growth per run** is what the state occupies divided by the runs it holds. That is an upper
  bound. It counts what an empty instance already occupies as if runs had written it. So the
  dates it gives come early, never late, and the bound tightens as runs accumulate.
- **Runs per day** are the runs created within a window (`TAKTUS_CAPACITY_WINDOW_DAYS`, 14 by
  default), divided by the window. For an instance younger than the window, its age is the
  window. It is never less than one day, so that an instance's first hour does not read as a
  rate of hundreds a day.

Why not two measurements, before and after runs? Because a difference needs a stored first
measurement, and a stored series is a table, a migration and a retention rule. The average over
everything the state holds needs nothing stored. It is exact about what the state holds and
conservative about what an empty state costs, which is the side to err on. It also measures from
the first day, with no history to wait for.

## 3. The report: a figure and a date

`governance/domain/service/capacity.py` turns an observation and the growth into findings. It is
pure and tested as a table. A finding reads like this:

> storage (database): 3.1 GiB free of 20.0 GiB (15.5 %); 1.4 MiB per run at most, over the 212
> runs the state holds; 31.0 runs/day over the last 14 days; full on 2026-12-12; below 10 % on
> 2026-10-26 — a person must act before 2026-10-26 (expanding this volume is impossible on its
> storage class: plan a migration)

Each finding has a status. *act* means a person must act. *ok* means nothing is to be done
before the next report. *unknown* means the platform did not say, and the finding says why.

**Storage is *act*** when the free share is below `TAKTUS_CAPACITY_STORAGE_WARN_PERCENT` (10 %),
or when the growth will take it there within `TAKTUS_CAPACITY_ACT_WITHIN_DAYS` (30). The
horizon is the time a migration needs, not the time a disk takes to fill. The remedy the
finding names follows `TAKTUS_CAPACITY_STORAGE_EXPANDABLE`: expand the volume, plan a migration,
or — untold — both, conditionally.

**Memory is *act*** below `TAKTUS_CAPACITY_MEMORY_WARN_PERCENT` (10 %). Where the instance starts
execution units on its own platform, the finding says how many more jobs of the unit's size fit.
**CPU is *act*** below `TAKTUS_CAPACITY_CPU_WARN_PERCENT` (10 %). A busy processor slows work down
and stops none, so a CPU finding is reported and never recorded.

**Where it appears.** `uv run taktusctl capacity` prints the report and exits 1 when a finding is
*act*. The daemon's scheduler makes the same report every `TAKTUS_CAPACITY_INTERVAL_SECONDS`
(3600) while it leads, and logs each finding — an *act* finding as a warning.

**What reaches the ledger.** A crossing does, not every report. When a storage or memory finding
turns to *act*, the report records `capacity.<resource>` — `capacity.memory`,
`capacity.storage.database`, `capacity.storage.state_directory` — with outcome `act`; when it
clears, the same kind with outcome `ok`. The newest entry of the kind is the state already
recorded, so a repeated report writes nothing. The entry goes to the chain of every tenant the
instance serves, because every tenant's work stands on the same platform. It names the adapter
that observed and, for storage, the bytes the state occupied as `consumption.storage_bytes`.
Nothing else: the ledger stays content-free (ADR-0006).

## 4. Admission against the platform

Admission control refuses a step whose estimate does not fit the budget (ADR-0005). It refuses a
job the platform cannot hold in the same way, before anything starts
(`run/domain/service/capacity.py`, `admit_capacity`):

- **memory** — a job that starts an execution unit on this platform needs the unit's memory limit
  plus `TAKTUS_CAPACITY_MEMORY_RESERVE_MB` (256) for everything else on the machine. With less
  free, the job is refused. The demand is the unit's own limit, `ExecutionUnit.limits.memory_bytes`.
  A worker reached by endpoint runs elsewhere and demands nothing here.
- **storage** — below `TAKTUS_CAPACITY_STORAGE_REFUSE_PERCENT` (2 %) free, a run is refused
  before it writes. The refusal share must lie below the warning share: a person is told before
  work is refused, never after. The settings refuse the opposite.

A quantity the platform did not observe refuses nothing. Refusing every job on a platform that
cannot be observed would stop all work silently, which is what this exists to prevent. It is not
passed over either: the verdict names it under `unobserved`, for the caller to record.

The function is built and tested. **The run engine does not call it yet**: that wiring is the
next change to `execute_run.py`, beside the budget admission of worker steps.

## 5. Every job carries a memory limit, and the limit is real

`ResourceLimits.memory_bytes` is mandatory on every execution unit. A limit nothing enforces is
worse than none, because it reads as a guarantee. So each execution adapter either enforces it
or refuses the job:

| Adapter | What holds |
|---|---|
| `container` | the engine's memory limit, with the swap limit set equal to it, so the job cannot swap. An engine that reports it cannot limit memory or swap (`/info`: `MemoryLimit`, `SwapLimit`) is refused before anything is created |
| `process`, on Linux | the unit is started through a launcher that sets `RLIMIT_DATA` to the limit and then becomes the unit. The limit holds for the unit and for every process it starts, per process |
| `process`, elsewhere | not enforceable: the job is **refused**, unless the operator sets `TAKTUS_EXECUTION_MEMORY_UNENFORCED=true`. That choice is in the startup log, and every launch logs it |
| cluster (next) | `resources.limits` on the job's pod; refuses a job it cannot give limits to (`deploy/k8s/README.md` §4) |

`RLIMIT_DATA` rather than `RLIMIT_AS`, because the second counts address space a runtime only
reserves. Runtimes that reserve gigabytes up front and never touch them would be refused at
start. Since Linux 4.7, `RLIMIT_DATA` counts every private writable mapping, which is the memory
a process actually takes.

## 6. Propose (`0.5.0`) — specification, not built

*Observe* says when a person must act. *Propose* says what acting would buy.

- **The marginal value of more capacity.** For each resource, what a larger allocation would
  change: the date the volume fills moves from D to D′; jobs refused for memory in the last 30
  days, and the blocked time they caused (`limit.compute` in [throughput.md](throughput.md)),
  would not have been refused.
- **Cost before and after.** What the platform costs now, what the proposal would cost, per
  month. The prices are configuration the operator supplies; Taktus never assumes a price.
- **The cheaper alternative first**, as throughput.md §4 requires: before proposing more disk, a
  retention rule for artifacts or logs that frees the same space. The ledger and the provenance
  are never candidates (ADR-0006, ADR-0021).
- **One proposal, one decision request.** Each proposal is a decision for a person, raised under
  the anchors of `docs/decisions/anchors.md`, with the figures above. A proposal is never acted
  on by the instance that made it; at `0.5.0` there is nothing to act with.

## 7. Manage (`0.7.0`) — specification, not built

*Manage* acts on the platform, within a budget a person set, where the environment permits.

- **What it may do.** Change an allocation the environment exposes to it and a person budgeted:
  enlarge a volume on a storage class that can, raise a namespace quota the instance was granted
  the right to raise, request a larger node from a platform that sells them. Each act is
  admitted against its budget like any step (ADR-0005), recorded in the ledger, and reported.
- **What it must never do.**
  - Never delete. No volume, database, backup, artifact or history — "never delete without
    asking" (CLAUDE.md §9) holds at every autonomy level, and a restore counts as a delete.
  - Never act with credentials that administer its own platform. An instance that could change
    the platform under it could break the path of its own repair (ADR-0025 §1, ADR-0013 C).
    Where the platform is the instance's own, *Manage* is a proposal to a person or to another
    instance that administers it, never an act.
  - Never let a probabilistic method decide an act on the platform. The trigger is a rule over
    the observed figures, as the automatic emergency stop is (ADR-0023).
  - Never exceed the budget, and never raise its own budget.
- **Where the environment does not permit it**, *Manage* degrades to *Propose*, and says so.

## 8. Where this ends

- **The observation is of this process's platform.** A container sees its own limits; the
  machine's are hidden where the container's are stricter. For execution units started in a
  cluster, the node or the namespace's quota is what counts, and the control plane's pod does
  not see it. That needs a platform adapter for the cluster, which arrives with the cluster
  execution adapter.
- **The database's free space is as good as the volume size it is told.** The figure also leaves
  out what the server keeps beside the database, the write-ahead log among it; the volume holds
  more than the database's size says.
- **Growth per run is an average over the instance's life.** A change in what a run writes — a
  new process that stores large artifacts — shows up slowly. Two measurements and their
  difference would show it at once; that is a stored series, and it arrives if the average
  proves too slow.
- **Memory on macOS is not observed**, and the `process` adapter enforces no limit there.
- **`RLIMIT_DATA` is per process, not per job.** A unit that starts four processes may take four
  times its limit. Only the container and cluster adapters limit a job as a whole.
- **A report runs every hour.** Anything that fills a volume faster than that is caught by the
  refusal at admission, not by the report.
