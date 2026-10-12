# NTC-0195 — A worker's unit reaches its own service's hosts

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-12
**Raised in:** the pull request for issue #269

## 1. What was decided

A launched worker — one whose execution unit the control plane starts per job, as a process, a
container or a Job in a cluster — now reaches the hosts its own service needs, beside the hosts
of the step's frame. ADR-0089 is the decision; this notice records the change of behaviour.

1. **The setting** is `TAKTUS_EXECUTION_SERVICE_HOSTS`, comma-separated hosts, per worker as
   `TAKTUS_WORKER_<NAME>_EXECUTION_SERVICE_HOSTS`, in the chart `execution.defaults.serviceHosts`
   and `serviceHosts` per worker. Each host is validated as a frame's host is.
2. **An assignment's job** reaches the frame's hosts and the service hosts. Before, it reached
   the frame's hosts alone.
3. **The conformance suite's unit** reaches the suite's hosts (`conformance.worker.hosts`) and
   the service hosts. Before, it reached no host at all.
4. **A probe** still reaches no host.
5. **The frame the worker receives** is the step's, unchanged; the worker still refuses a tool
   call outside it (W-13).
6. **P-03 is version 6.** Its statement of autonomy now says that the unit reaches the frame's
   hosts and the service hosts the operator configures. Nothing else of it changed.

With the setting unset, which is the default, every job reaches exactly what it reached before.

## 2. The evidence

- The installed instance, 2026-10-12: the coding worker on the cluster kind reached the
  repository's host and not its agent's provider, and could do nothing. Issue #269 states it.
- `adapters/driven/workers/launched.py` before this change passed `assignment.frame.allowed_hosts`
  as the job's hosts, and `composition/conformance.py` started the suite's unit with none.
- `tests/adapters/workers/test_launched.py` holds points 2 and 4;
  `tests/composition/test_service_hosts.py` points 3 and the recorded configuration;
  `tests/adapters/execution/test_kubernetes.py` that the cluster's proxy admits the hosts and
  that a cluster without enforced network policies refuses them;
  `tests/composition/test_settings.py` the setting; `tests/governance/test_chart.py` the chart.

## 3. What was considered

- **The suite's unit with the service hosts alone**, as the issue's brief first put it. Not
  taken: the suite's task reaches `conformance.worker.hosts` as a frame's hosts are reached, and
  a unit that cannot reach them tests a worker that cannot work. W-13 then also tests the
  worker's own refusal rather than the network's.
- **P-03's statement left at version 5.** Not taken: it said the unit reaches "exactly the hosts
  and credentials the frame names", which is no longer true where service hosts are configured.
  Editing the text of version 5 in place would make one version mean two things on an instance
  that registered it; a new version is the honest record.
- **The alternatives to the design itself** are in ADR-0089.

## 4. Which entry permits it

M2.4 of `docs/decisions/anchors.taktus.md`: "A change of what the software does, made inside an
agreed scope, that breaks no contract, moves no limit or autonomy level and says nothing
public." The scope is issue #269. No contract changes: the worker contract's frame and its
checks are as they were, and the execution port is internal. No limit moves: the frame, which
is the step's bound, is unchanged, and the default adds no host; what a unit may reach beyond
it is the operator's configuration, as its image and its credentials are. P-03's autonomy level
stays 4; only the statement of its reason is corrected. Nothing public is said.
