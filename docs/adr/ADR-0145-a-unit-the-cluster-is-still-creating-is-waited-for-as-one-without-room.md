# ADR-0145 — A unit the cluster is still creating is waited for as one without room

**Status:** accepted · amends ADR-0037 §6 (no room for the unit makes the step wait) · issue #634

## Context

A launched worker starts an execution unit for each assignment and for each question it is
asked, such as what it offers. The unit has a bound within which it must answer its health
check: `start_timeout_seconds`, 120 seconds on the cluster. Past it, the cluster adapter asks
the cluster why, and fails the launch with that reason.

ADR-0037 §6 made one reason a wait instead of a failure: no node has room for the unit, which
the scheduler names as `Insufficient <resource>`. Every other reason stayed a failure. Since
issue #590, a worker that cannot be asked what it offers fails its step.

On the instance's install of 2026-10-28, two runs started in the same minute. Both escalated
with "did not answer health within 120s; the cluster says: ContainerCreating". The unit's image
was new on the node and was being pulled. Nothing was broken: the unit was not ready yet.

## Decision

### 1. A placed unit whose containers are still being created is at capacity

When a unit did not answer health within its bound, the cluster adapter raises
`ExecutionAtCapacity`, and no longer a plain `ExecutionError`, where the cluster says one of:

- `ContainerCreating`: the node creates the container, which includes pulling its image;
- `PodInitializing`: the pod's init containers still run;
- `Pending`: the pod is placed on a node, and none of its containers has a state yet.

The message starts with "the unit is still being created" and carries the cluster's reason.

### 2. The step waits as for a platform without room

The launched worker answers `WorkerAtCapacity`, as ADR-0037 §6 says. The step goes back to its
boundary, and the run halts with cause `capacity`. Its runner tries again after a delay. This
holds for the question what the worker offers, for its estimate and for the assignment.

### 3. The wait is bounded by the step's capacity ceiling

The bound is the one every wait at capacity has: the step's `capacity_ceiling_seconds`, or
the engine's, an hour by default (ADR-0037 §5). Past it the step fails with cause `capacity`.
Its reason carries the cluster's, for example `ContainerCreating`.

### 4. What still fails at once

A unit that runs and answers nothing fails as before (#590). So does a unit whose image cannot
be pulled (`ErrImagePull`, `ImagePullBackOff`), whose container cannot be created, or that no
node may take at all, such as for a taint.

## Alternatives

- **Waiting longer inside the launch.** The runner would hold the run for as long as the image
  takes, and a slow pull would block a runner's place. The wait at capacity frees it.
- **A cause of its own.** The cause `capacity` already has its account, its ceiling, its
  deferral and its reports (ADR-0037, ADR-0043). A second cause would duplicate all of them for
  a state that ends the same way: the unit becomes ready, or the ceiling passes.
- **A longer health bound.** It would delay the failure of a unit that is really broken by the
  same amount.

## Consequences

- `still_creating` and `CREATING` in the cluster adapter; `ClusterJob.waiting` names a placed
  pod without container states as `Pending`.
- A step whose unit is still being created halts its run with cause `capacity`, where it failed
  before.

## Where this promise ends

Only the cluster adapter recognises a unit that is still being created. The process and
container adapters start a unit or fail. The reason is read from the container's waiting
reason and the pod's phase, as the cluster reports them when the health bound has passed. A
cluster that words them otherwise makes the step fail as before.

The launch that waited removes its pod. The next try creates another. An image the node
finished pulling is kept by the node, so the next try usually starts faster. A pull that
never finishes keeps the step waiting until its ceiling. A unit that is stuck in creation for a
reason the cluster does not name, such as a volume that cannot be mounted, waits until its
ceiling too, and then fails with the cluster's reason.
