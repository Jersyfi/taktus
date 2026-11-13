# ADR-0312 — A canary on a serverless platform takes a share of the traffic

**Status:** accepted · extends ADR-0211 (a serverless workload) and ADR-0195 (a deployment
through a workload cluster's API) · issue #438, UC-03 B-8.04, §8 "deployment targets with
rollback"

## Context

B-8.04 raises a release in stages while its error rate holds, and halts it by itself on a rise.
On a cluster the canary is a deployment of its own, and a stage is a number of replicas
(`deployment.workloads.scale`). At an app store a stage is a share of the users
(`stores.releases`, ADR-0210).

A serverless platform has neither. It starts instances itself, so it has no replicas to set
(ADR-0211). What it has is traffic: a service holds several revisions, and its traffic is a list
of revisions, each with a percentage. ADR-0211 left B-8.04 off that platform, because no
operation set such a split.

## Decision

### 1. `deployment.workloads.split` shares the traffic between a canary and the stable revision

The serverless connector serves a fourth operation of `deployment.workloads`:

| Input | Meaning |
|---|---|
| `name` | the service |
| `percent` | the canary's share, a whole number from 0 to 100 |
| `revision` | the canary; without it, the service's latest ready revision |

The stable revision is the other ready revision that takes the most traffic now. The canary gets
`percent`, the stable revision the rest. 100 promotes the canary to all traffic. 0 puts all
traffic back on the stable revision. A canary that is not ready, or a split below 100 without a
stable revision beside it, is `not_found`, and nothing is written.

The write is `marked` like the rollback: the key is an annotation of the service, and a repeat
that finds it is `replayed`. The template is left as it is, so no revision is made. The output is
the service as a read gives it, with `traffic`: each revision and its share.

The operation keeps the capability's name, so a process names `deployment.workloads` as it does
on a cluster. The cluster's connector does not serve it. A cluster has no traffic split of its
own; one needs a service mesh or an ingress controller, each with its own API.

### 2. B-8.04 has a version for a serverless platform

`B-8.04-traffic-canary.yaml` is a third bundle of the process `b-8-04`, beside the cluster's and
the store's versions. A tenant keeps the one its release runs on. It has three stages. In each
stage, `split` sets the canary's share to the stage's percentage. The run then waits ten
minutes, reads the canary's error rate with the tenant's query, and compares it with the limit
by the rule `filter` (`exact`).

- **On a rise,** `split` to 0 puts all traffic back on the stable revision. The rise is a rule,
  never a probabilistic method (ADR-0023), and the later stages are skipped.
- **When the third stage holds,** `split` to 100 promotes the canary.

The process starts at level 2, at which a person confirms every step. Its target in UC-03 is
level 3.

### 3. The canary is deployed by the business's build

The business's own build deploys the canary revision beside the stable one without traffic
(the platform's `--no-traffic`). The process shares traffic and builds nothing.
`deployment.workloads.release` keeps its meaning: a new revision that takes all traffic. A
release that should start as a canary therefore does not go through it.

## Alternatives

- **A release that takes a share.** An input `percent` on `release` would let one operation
  both make a revision and split traffic. The cluster's `release` cannot honour it, and the
  same operation name would then mean two different things on the two targets.
- **The rollback as the halt.** The rollback puts all traffic on the revision before the one
  serving. While traffic is split, no single revision serves it all, so the rollback cannot
  tell which revision is the stable one. A split to 0 names it.
- **A split on the cluster through a mesh.** It needs a product beside the cluster, with an API
  of its own. That would be a connector of its own, for a tenant that runs one.

## Consequences

- `connectors/taktus_connectors/cloudrun/` declares and serves `deployment.workloads.split`. Its
  fake under `tests/fakes/serverless_service.py` deploys a revision without traffic
  (`POST /_fake/deploy`) and reports the traffic per revision. The shipped list carries the
  operation.
- `blueprint.yaml` names the new bundle as `B-8.04-serverless`, an alternative of B-8.04.
- The blueprint's README no longer says that B-8.04's canary does not run on a serverless
  platform.

## Where this promise ends

- **One canary at a time.** A split shares the traffic between two revisions. Traffic already
  spread over three or more is replaced by those two. A tag of a revision, which the platform
  offers for testing it by its own address, is dropped.
- **No canary on a cluster or a site through this operation.** The cluster keeps its replicas.
  A hosted site has no traffic split in `deployment.sites`.
- **The canary is not made here.** A release whose canary the build did not deploy has none.
  The run then halts at the first split with `not_found`.
- **The error rate is the tenant's query.** Telling the canary's errors from the stable
  revision's is the metrics store's job, through a label the platform gives each revision.
  A query that mixes them judges both together.
- **The platform's rollout is not awaited.** A split answers before the platform has moved the
  traffic. The ten-minute wait covers that move. A stage whose traffic had not moved by then is
  judged on less traffic than its share.
