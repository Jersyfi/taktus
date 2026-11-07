# ADR-0211 — A deployment target that is not a cluster is a serverless workload or a hosted site

**Status:** accepted · extends ADR-0195 (a deployment through a workload cluster's API) and
ADR-0024 (idempotency) · issue #438, UC-03 §4.8, §8 "deployment targets with rollback"

## Context

ADR-0195 releases, checks and rolls back a deployment of a cluster. UC-03 §8 still says "any
other target: no". A small software business often runs no cluster: its backend runs on a
serverless platform that runs containers, and its web front end is a site a hosting service
builds and serves. B-8.05 and B-8.06 must run on those too.

Two shapes cover them. A **serverless workload** is a container image released as a new
revision, with traffic on a revision; the most widely used platform of that kind publishes an
Admin API with services, revisions and traffic. A **hosted site** is a version the business's
own build uploaded, which the host publishes; the most widely used hosts publish a version,
put it live, and put an earlier one back, each through its API.

## Decision

### 1. A serverless workload serves `deployment.workloads`

A connector `cloudrun` serves `deployment.workloads.read`, `.release` and `.rollback` with the
inputs and outputs of the cluster's connector, so that B-8.05 and B-8.06 run on it unchanged,
under the same credential name. A release sets the container's image on the service's template,
which makes a new revision, and puts all traffic on the newest; the key is an annotation of the
template, found again on the service or a kept revision. A rollback puts all traffic on an
earlier revision and makes none; its key is an annotation of the service. `rolled_out` is the
platform's own: the service no longer reconciling, its condition succeeded, the newest revision
ready and serving all traffic. There is no `scale`: the platform starts instances itself.

### 2. A hosted site serves a capability of its own, `deployment.sites`

A site has no container and no replica, so it is a sibling capability, not the workloads':

| Operation | Effect | What it does |
|---|---|---|
| `deployment.sites.read` | read | which version is live, and for a named version its state and `rolled_out`: ready and live |
| `deployment.sites.release` | write | a version the host already built put live |
| `deployment.sites.rollback` | write | an earlier version, named, put live again |

Three connectors serve it, one per host: `firebase`, `netlify` and `vercel`. A tenant runs the
one of its host. B-8.05 gains a version for a site, `B-8.05-site-deployment.yaml`, of the same
process `b-8-05`: it reads the live version first, so that the rollback names it, then releases,
waits for `rolled_out`, runs the smoke test and puts the rollback to a person.

### 3. Where a host has no place for the key, the write is `none`

One host keeps a release's message, and the key's mark goes there: `marked`. The other two
publish a version by a request without a body. Their writes are declared `none` (ADR-0024 §3):
the engine never repeats them on its own, and a run that stopped inside one goes to a person. The
connector still reads the live version before it writes, so a repeat a person starts for a
version already live changes nothing and reports `replayed`.

## Alternatives

- **Every target under `deployment.workloads`.** A site has no image and no container to name;
  the inputs would mean nothing there, and a process could not tell the two apart.
- **A state-marked write declared `marked`.** The suite's repeat with a new key must act again,
  and a state cannot: a `marked` declaration would claim a key the host never sees.
- **A deployment tool over every host.** One more product, and each host's own API is under it.

## Consequences

- Connectors `cloudrun`, `firebase`, `netlify` and `vercel`, their fakes under `tests/fakes/`,
  their scenarios and images, in the shipped list and the chart's list; `SITES_TOKEN` in
  `CREDENTIALS.md`, and `WORKLOADS_TOKEN` as a service account key for the serverless platform.
- `B-8.05-web-deployment.yaml` and `B-8.06-backend-deployment.yaml` allow 200 quota units: a
  serverless read costs more than a cluster's, and the wait for the rollout holds sixty reads.
- The conformance harness generates a service account key per run, its token endpoint the fake's.

## Where this promise ends

- **No canary on a serverless workload or a site.** B-8.04 raises a canary's replicas; a split of
  traffic between revisions is not served, and B-8.04 runs on a cluster or a store only.
- **A rollback on a serverless workload moves traffic, not the template.** The service's
  template stays the failed release's, and the next release replaces it; a revision the platform
  no longer keeps cannot be put back.
- **A rollback of a site needs the earlier version named.** The process names the version it read
  before the release; a site whose live version was unknown then has no rollback.
- **Two hosts' writes are not repeated by the engine.** A run that stopped inside a publish goes
  to a person, who sees in the host whether the version went live.
- **The build is the business's.** A version is uploaded by its own build; the processes publish
  what was built and build nothing.
