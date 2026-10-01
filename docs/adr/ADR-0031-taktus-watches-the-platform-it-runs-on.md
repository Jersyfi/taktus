# ADR-0031 — Taktus watches the platform it runs on

**Status:** accepted · applies ADR-0013 A and ADR-0005 to the machine under an instance

## Context
At autonomy level 4 a business's work depends on an instance running. The machine under it has
a fixed amount of memory, processor time and disk. On the first target there is no swap, so a
process that needs more memory than is left is killed by the kernel without a message. The
database's volume cannot be enlarged after it was created there, and the ledger only grows
(DEC-0033). Until now nothing in Taktus looked at either. An execution unit's memory limit was
a number the process adapter did not enforce, and a full volume would have been discovered by
the run that failed on it.

The owner's principle: Taktus keeps an eye on its own platform and tells a person when they
must act, so that work never silently stops.

## Decision
1. **A platform port** reports CPU, memory and the state directory's storage as free of total,
   each with its source. A quantity an adapter cannot observe is `Unobserved` with the reason;
   it is never estimated. The database's size is the persistence port's (`StateSize`); the
   volume under it is told by configuration.
2. **Growth per run** is the state's size over the runs the state holds, and runs per day are
   counted from the ledger over a window. The report turns both into dates: when a volume is
   full, and when it falls below the warning share. A finding is *act* below the share, or when
   the growth will take it there within the configured horizon. The report is a figure and a
   date, never a warning light.
3. **A crossing is a ledger entry**, `capacity.<resource>`, with outcome `act` or `ok`, in the
   chain of every tenant the instance serves. A repeated report writes nothing.
4. **Admission refuses a job the platform cannot hold**, as it refuses a step the budget cannot
   hold: memory for the unit plus a reserve, and storage above a refusal share that lies below
   the warning share. An unobserved quantity refuses nothing and is named.
5. **Every execution unit's memory limit is enforced, or the job is refused.** The container
   adapter sets the swap limit equal to the memory limit and refuses an engine that cannot
   limit either. The process adapter enforces `RLIMIT_DATA` on Linux and refuses elsewhere,
   unless the operator accepts an unenforced limit explicitly.
6. **Three stages.** *Observe* is built with this ADR. *Propose* (`0.5.0`): the marginal value
   of more capacity, with the cost before and after. *Manage* (`0.7.0`): acting within a budget
   where the environment permits — never deleting, never with credentials that administer the
   instance's own platform (ADR-0025). `docs/architecture/platform.md` specifies both.

## Alternatives
- **Leave it to the platform's monitoring.** A cluster's monitoring knows the node, not the
  growth per run, and it tells whoever reads its dashboard, not the person the instance reports
  to. Taktus would still start jobs that cannot fit.
- **Store a series of measurements and difference them.** More precise about a recent change in
  growth; it needs a table, a migration and a retention rule, and gives nothing on the first day.
- **`RLIMIT_AS` for the process adapter.** It counts reserved address space and refuses the
  runtimes the coding worker is built on.

## Consequences
- `taktusctl capacity` and the scheduler report; the thresholds are `TAKTUS_CAPACITY_*`
  settings with named defaults.
- On macOS the process adapter refuses a job unless `TAKTUS_EXECUTION_MEMORY_UNENFORCED=true`.
- The run engine holds a worker step against the platform beside the budget, and a run against
  its storage before its first step.

## Where this promise ends
The observation is of the instance's own process. A container sees its own limits; for units
started in a cluster the node's or the namespace's quota counts, which the control plane's pod
does not see until a cluster platform adapter exists. The database's free space is only as good
as the volume size it is told, and it leaves out the write-ahead log. Growth per run is an
average over the instance's life, so a sudden change in what runs write shows slowly, and a
volume filled faster than the report interval is caught only by admission. `RLIMIT_DATA`
limits each process of a unit, not the unit as a whole. On macOS memory is neither observed nor
limited. CPU is reported and never refuses anything.
