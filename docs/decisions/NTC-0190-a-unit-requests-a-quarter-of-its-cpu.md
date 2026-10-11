# NTC-0190 — A unit requests a quarter of its CPU

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-11
**Raised in:** the pull request for issue #244

## 1. What was decided

The cluster execution adapter starts each execution unit as a Job in the cluster
(`deploy/k8s/README.md` §7). A pod tells the cluster's scheduler two things per resource: what
it *requests*, which the scheduler reserves on a node, and its *limit*, which it may use. Until
now a unit requested exactly its limits, for CPU and for memory.

Now a unit requests a share of its CPU limit and all of its memory limit:

1. **The share is a setting**, `TAKTUS_EXECUTION_CPU_REQUEST_SHARE`, between 0.01 and 1, per
   worker as every execution setting is (ADR-0078). The chart takes it as
   `execution.defaults.cpuRequestShare` and per worker as `cpuRequestShare`.
2. **Its default is 0.25.** A unit with the default limit of 1 CPU requests 250 millicores.
3. **A share of 1 restores the old behaviour**: the request is the whole limit.
4. **The limits do not move.** The CPU limit, the memory limit and the wall clock are what they
   were. The memory request stays the memory limit, because memory is not compressible and the
   node has no swap.
5. **A request is never below one millicore**, whatever the share and the limit.

## 2. The evidence

- The install of #66 on 2026-10-11, as the issue states it: on the instance's node, one unit
  fitted, and a second waited with `FailedScheduling: insufficient cpu`, while 3.5 of 4 cores
  were idle. The whole node, the running unit included, used about half a core.
- A unit of the coding worker spends most of its wall clock waiting for a model's answer or for
  the network. CPU it requested and does not use is reserved for nobody else.
- With a quarter, the memory request decides how many units fit before CPU does on the node the
  issue describes: its free CPU holds six units at a quarter of a core, its free memory two at
  the default of 1 GiB. Memory is the resource a unit is killed for, so it should be the one that
  decides.
- `tests/adapters/execution/test_kubernetes.py` holds the rendered pod spec: the CPU request at
  the share of the limit, the memory request at the limit, the limits unchanged, a share of 1 the
  whole limit. `tests/composition/test_settings.py` holds the default and the range;
  `tests/governance/test_chart.py` holds the rendered configuration.

## 3. What was considered

- **A share of 0.5.** Rejected as the default: on the issue's node it fits three units by CPU,
  still more than memory allows, and reserves twice as much for no measured need. An operator
  whose units compute more sets it.
- **A share of 0.1.** Rejected: a unit that does compute — a build, a test suite — would get a
  tenth of a core whenever the node is busy, and its wall clock does not stretch with it. A
  quarter keeps a busy node from slowing a unit to a crawl.
- **No CPU request at all.** Rejected: the scheduler would then place units without regard to
  CPU, and under contention a unit would get almost nothing.
- **A memory request below the limit too.** Rejected by the issue and by the node: memory is not
  compressible, there is no swap, and a unit must not be killed for memory another pod took.
- **A fixed request in millicores instead of a share.** Rejected: a worker that sets a larger
  limit would keep the same small request, and the setting would have to change with every limit.

## 4. Which entry permits it

M2.4 of `docs/decisions/anchors.taktus.md`: "A change of what the software does, made inside an
agreed scope, that breaks no contract, moves no limit or autonomy level and says nothing public."
The scope is issue #244, which asks for a share "with a default below the limit". No contract
changes: the execution port and the worker contract are untouched. No limit moves: a request is
the scheduler's reservation, not a bound on what a unit may use, and every bound of M3.10 — the
CPU and memory limits, the wall clock, the budget and its margin — stays as it was. Admission
counts no CPU, from a limit or a request (`deploy/k8s/README.md` §7). Nothing public is said.
