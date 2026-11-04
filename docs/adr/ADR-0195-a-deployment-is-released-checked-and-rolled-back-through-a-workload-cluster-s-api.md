# ADR-0195 — A deployment is released, checked and rolled back through a workload cluster's API

**Status:** accepted · extends ADR-0111 (connectors over open standards), ADR-0158 (a connector
is an image of its own) and ADR-0192 §2 (the processes of software-operations) · issue #438,
UC-03 §4.8, §8 "deployment targets with rollback"

## Context

UC-03 stage 3 is release without people: a staged rollout raised by an error corridor and halted
on a rise (B-8.04), a web deployment with a smoke test and a rollback on failure (B-8.05), a
backend deployment whose error rate is watched for thirty minutes before a rollback is proposed
(B-8.06), and a reminder for a release pull request open past its limit (B-8.07). UC-03 §8 says no
connector serves a deployment target with rollback.

A deployment target must be reached through an interface that serves many tenants, never through
one tenant's own scripts (DEC-0225). The Kubernetes API is an open-source, vendor-neutral
interface that every major cloud and every self-hosted cluster serve alike. Its `Deployment`
resource keeps a revision history of its pod templates as `ReplicaSet`s. A rollback is therefore
the cluster's own record, not a copy the connector keeps. The app stores' interfaces are each one
vendor's and differ in what a staged rollout is; they are not built here.

## Decision

### 1. A connector serves `deployment.workloads`

A connector under `connectors/taktus_connectors/kubernetes/` serves four operations against one
namespace of a cluster's API, with the requesting identity's bearer token:

| Operation | Effect | What it does, and how a repeat is recognised |
|---|---|---|
| `deployment.workloads.read` | read | one deployment: its containers with their images, the replicas wanted, updated, ready and available, its revision, and `rolled_out`: the controller has seen the newest change and every wanted replica is updated and available, the condition `kubectl rollout status` waits for |
| `deployment.workloads.release` | write, `marked` | one container's image set, the key as an annotation of the pod template. The lookup reads the deployment and its revisions: a template that carries the key, current or in the history, is the original, replayed. The change carries the deployment's `resourceVersion`; a deployment changed in between is `conflict` |
| `deployment.workloads.rollback` | write, `marked` | the pod template of an earlier revision put back: the one named, or the newest before the current. The key is an annotation of the restored template, and the lookup is the release's. No earlier revision is `not_found` |
| `deployment.workloads.scale` | write, `marked` | the replicas wanted set. The deployment's own number is the mark: a repeat that finds the number set changes nothing and reports `replayed`. Weaker than a key, and stated so, as for a label (ADR-0097) |

### 2. The release processes are rules over the cluster, the check and the metrics

B-8.05 and B-8.06 release the image, wait until `rolled_out`, and then judge. B-8.05 runs the
smoke test, one `check.http.run`. B-8.06 waits thirty minutes and reads the error rate through
`metrics.series.query`. A failed smoke test, or a rate above the version's limit, counts as a
failure by rule. The rollback then runs only after a person confirmed it: confirming the rollback
stays with a person (UC-03 B-8.05, B-8.06). The step carries `ask` (ADR-0088), at every level.

B-8.04 raises a canary deployment's replicas in the version's stages. It reads the canary's error
rate after each stage, and continues only while the rate is below the version's limit. On a rise
it scales the canary to zero by itself: the halt is the process's, and needs no person. Resuming
after a halt stays with a person, who starts a new run.

## Alternatives

- **A deployment tool's own interface (a GitOps controller, a progressive-delivery controller).**
  Each is one product among several, and a tenant without it has none. The workload API is under
  all of them.
- **Rollback by setting the previous image.** A revision is more than an image: environment,
  resources, probes. The cluster's history holds the whole template.
- **A halt by the corridor itself.** A corridor judges a signal after the run and reports. The
  halt must happen inside the run, between two stages, so it is a rule over the reading, and the
  corridor reports beside it.
- **A connector over a command-line tool.** It would make the connector's image carry the tool
  and read a configuration file of credentials. The API over HTTP takes the token per call.

## Consequences

- A connector `kubernetes`, its fake under `tests/fakes/workload_cluster.py`, its scenario and its
  image, in the shipped list and the chart's list.
- `blueprints/software-operations/processes/` gains B-8.04, B-8.05, B-8.06 and B-8.07.

## Where this promise ends

- **One namespace, deployments only.** Stateful sets, jobs and other resources are not served.
  A tenant whose service runs on another kind has no release process here.
- **A rollback restores a template; it creates a new revision.** The key annotation makes the
  restored template differ from the earlier one, so the cluster records the rollback as the
  newest revision rather than reusing the old one. The images and settings are those of the
  earlier revision.
- **A revision is kept only as long as the cluster keeps it.** The deployment's revision history
  limit bounds how far back a rollback reaches.
- **A rollout that never completes goes to a person.** The wait for `rolled_out` has a timeout;
  past it the run fails, and no rollback is started for it.
- **The canary's error rate is the tenant's query.** The process reads what the query answers;
  a query that does not measure the canary alone measures something else.
- **Scaling recognises its repeat by the number.** A repeat after somebody else scaled to the
  same number reports replayed; a repeat after somebody scaled to another number scales again.
- **App stores are not served.** Store submission, beta distribution and a store's staged
  rollout (B-8.02, B-8.03, B-8.04 for a mobile app) need one vendor's interface each.
