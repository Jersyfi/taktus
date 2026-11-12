# ADR-0201 — The repository's infrastructure is read, and a lost run restarted

**Status:** accepted · extends ADR-0193 (keeping a pull request mergeable), ADR-0195 (a
deployment through a cluster's API) and ADR-0024 (effect and idempotency) · serves UC-03
B-1.04, B-1.11, B-1.12, B-2.03, B-7.10 · issue #447

## Context

Stage 1 of UC-03 left five rows of the repository and the deployment unbuilt, each for a reason
the blueprint's README named:

- B-1.12 could name a hung pipeline run but not restart it, and could read no runner.
- B-2.03 read the quotas a metrics store holds, but not the repository service's own rate limit,
  which only the service reports.
- B-7.10 counted idle pull requests, but no connector listed the branches without one.
- B-1.11 had no reading of the repository's dependency advisories.
- B-1.04 could not tie an error rate to the last deployment: no reading stated when the last
  release was rolled out.

The repository hosting service the connector speaks publishes each of these in its REST
interface. The cluster's API states when a deployment's rollout last progressed.

## Decision

### 1. Four reads of the repository

The `github` connector adds four reads, each one request per page of 100, at most ten pages:

| Operation | Capability | What it reads |
|---|---|---|
| `repository.runners.list` | `repository.runners` | the self-hosted runners: name, operating system, online or offline, busy, labels |
| `repository.branches.list` | `repository.branches` | the branches: name, head commit, protected |
| `repository.ratelimit.read` | `repository.ratelimit` | the requesting identity's limits per resource, with the share used as decimal text |
| `repository.advisories.list` | `repository.advisories` | the dependency alerts: advisory, package, vulnerable range, first patched version |

No answer names a person. An alert's dismisser, its assignees and a dismissal's requester are
never copied (principle 14). The share used is rounded down to four decimal places in integer
arithmetic, so that a rule comparing it is `exact` (CLAUDE.md §4).

### 2. Two writes of one run, idempotent by the run's own state

`repository.pipelines.rerun` reruns the failed jobs of one completed run. The service keeps no
mark on a run, so the call names the attempt it read. A run whose attempt is higher was rerun
since that reading, and the repeat changes nothing and reports `replayed`.
`repository.pipelines.cancel` cancels one queued or running run. A run completed already is the
repeat's answer, `replayed`. Both are declared `marked` with that weakness stated, as the
cluster's scale is (ADR-0195): a rerun or a cancel by somebody else reads the same.

A run that is not completed cannot be rerun. The call is a conflict and writes nothing. A hung
run is therefore cancelled first and rerun after, in two steps a process orders.

### 3. A deployment states when its rollout last progressed

`deployment.workloads.read` adds `changed_at`: the `lastUpdateTime` of the deployment's
`Progressing` condition. The controller sets it as the newest replica set comes up. Once the
rollout is complete, it is the moment the last release finished rolling out. A process reads
the errors since that moment.

## Alternatives

- **The service's deployments interface for the moment of a release.** It knows only the
  deployments a workflow reports to it. The cluster knows every rollout, whoever made it.
- **Rerun the whole run.** A rerun of the failed jobs repeats only what failed. A run whose
  every job failed is rerun whole by the same call.
- **Force-cancel.** It bypasses the conditions a workflow declares for its end. It stays with a
  person.
- **The service's own security advisories of a repository.** They are what the repository
  publishes about itself. The dependency alerts are what affects it.

## Consequences

- The `github` connector's capabilities grow by three, `repository.runners`,
  `repository.ratelimit` and `repository.advisories`; its fake serves them.
- B-1.04, B-1.11, B-1.12, B-2.03 and B-7.10 are built or extended (UC-03 §8).

## Where this promise ends

- **One repository.** The runners of an organisation, its rate limits shared across
  repositories and its advisories elsewhere are not read.
- **A lost run is a run, not a job.** The service does not say a job was lost to its runner.
  A run in progress past the tenant's limit is what a process treats as lost.
- **No runner is removed.** Removing one changes the pool, whose size stays with a person
  (UC-03 B-1.12).
- **The weekly cost of the pipeline is not read.** The service's billing interface is the
  account's, not the repository's, and no capability serves it.
- **`changed_at` is the condition's moment.** A deployment changed by a means that leaves the
  condition as it was, such as a change of its replicas alone, does not move it.
