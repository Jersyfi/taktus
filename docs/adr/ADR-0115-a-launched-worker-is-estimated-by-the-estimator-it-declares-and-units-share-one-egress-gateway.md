# ADR-0115 — A launched worker is estimated by the estimator it declares, and units share one egress gateway

**Status:** accepted · amends ADR-0005 on how a launched worker is estimated (§*Eighth
amendment* there points here) and replaces the per-job egress proxy of the `container` and
`cluster` execution adapters · issue #324, `docs/research/2026-10-12-devops-review.md` §E2,
DEC-0187

## Context

A launched worker exists only while a job does: an execution adapter starts a unit for it. The
engine asks every worker step for an estimate before admission (ADR-0005, third amendment). A
launched worker answered that question with a *probe*: a unit started with no credential and no
host, asked, and ended. Every worker step therefore started two units, the probe and the
assignment's.

Each unit also brought its own egress. The `container` adapter created a network, an egress
container and the unit's container per job. The `cluster` adapter created a Job and a Service
for an egress proxy beside the unit's Job and Service, and a Secret with the proxy's token.

The review of 2026-10-12 measured it. With the container adapter, a worker step spent 2.28 s
starting and stopping units against 0.33 s of work. Against a fake of the cluster's API, a
worker step created three Jobs, three Services and a Secret, in 29 API calls.

## Decision

**1. A worker declares its estimator in its capabilities.** `contracts/worker/v1` gains an
optional `estimator` in `Capabilities`. Two kinds exist:

- `fixed`: every assignment is estimated as the `estimate` it names;
- `per_item`: `each` once for every item of the list `task.inputs[input]`, and `otherwise` where
  the task carries no such list or an empty one. Every quantity, `wall_seconds` and `steps` are
  multiplied by the number of items.

An estimator yields an `Estimate` of the contract's shape, so nothing downstream of it changes.

**2. A launched worker is estimated by its estimator alone.** The launched-worker adapter asks
the capabilities once, through one probe, and keeps the answer for its life. For each estimate
it applies the declared estimator to the request and starts no unit. The engine calibrates what
the estimator yields from the ledger, per adapter, exactly as it calibrates an answer of
`POST /v1/estimate` (ADR-0005, third amendment, point 4). No unit starts before admission.

**3. A launched worker that declares no estimator is refused, not probed.** Its estimate raises
`NoEstimator`, and the engine refuses the step for want of an estimate (`step.rejected`, outcome
`no_estimate`). This is the rule the third amendment of ADR-0005 set for every step that cannot
be estimated. A worker reached by endpoint is still asked at `POST /v1/estimate`: asking it
starts nothing.

**4. An estimator yields no less than the worker's own answer.** The worker holds its own
estimate against the limits it is given (W-10). An assignment admitted at a lower estimate
would be rejected by the worker after admission. So W-02 now also holds a declared estimator to
the worker's answer for the same request, in every quantity and in `wall_seconds`.

**5. Units reach their hosts through one gateway of the instance.** The gateway is an HTTP proxy
that admits a request only with a token, and only to the hosts that token names. The execution
adapter mints the token per job: the job's hosts, and the time after which it admits nothing,
signed with the gateway's key by HMAC-SHA256. The unit receives it as the password of its proxy
variables, in memory, as it receives a credential. A unit that presents no token, a token the key
did not sign, or a token whose job's time is over is answered 407. A host its token does not name
is answered 403. A job without hosts gets no token and no proxy variable, and reaches nothing.

- In the **cluster**, the gateway is a Deployment of the chart in the execution namespace, behind
  a Service, from the control plane's image. Its key is an existing Secret in both namespaces:
  the gateway checks tokens with it, and the runner signs them with it
  (`execution.gateway.key`). The namespace's policies hold for it as they held for the per-job
  proxy: units reach it, and it reaches only the allowed ports outside the cluster's ranges.
- In a **container** engine, the gateway is one container per gateway key. It joins each job's
  internal network for the job's life. It also forwards the control plane's requests to a unit's
  worker contract. It listens for those only on the network it started on, never on a job's, and
  it refuses every address on a job's network whatever a token names. Without a configured key, a
  key is drawn for the process, and the process removes its gateway when it closes.

**6. What a step starts, measured.** With the container adapter, a worker step now starts one
container and one network, against two containers and a network per unit before, for two units.
In the cluster, a worker step creates one Job, one Service and one Secret, against three Jobs,
three Services and a Secret before. On the installed instance, pod starts per worker step are
measured before and after the release, and recorded on the pull request.

## Alternatives

- **Cache a probe's estimate per worker.** That keeps a unit start per worker and step kind, and
  an estimate that depends on the task would be wrong for every other task.
- **Ask the assignment's unit for its estimate, then admit.** The unit would start before
  admission, with the job's credentials. ADR-0005 starts nothing with credentials before
  admission has said yes.
- **A sidecar proxy in the unit's pod.** Containers of one pod share a network, so the unit could
  bypass its own proxy. The per-job proxy was a Job of its own for that reason.
- **One gateway that looks up each job's hosts in a registry.** That needs a store the gateway
  reads and the runner writes, and the gateway would need rights in the cluster's API. A signed
  token carries the hosts itself; the gateway holds nothing but its key.

## Consequences

- A worker step starts one unit. The estimate is at once and costs nothing.
- The coding workers declare a `fixed` estimator, the estimate they answer for every
  assignment. The reference worker declares a `per_item` estimator over the commands of its
  task. The ML bench declares none; it is reached by endpoint.
- The cluster adapter needs a gateway key and the gateway's Service where a job names hosts; it
  refuses such a job without them, before creating anything. Its Role gains `get` on Services,
  to read the gateway's address.
- An instance upgraded to this version needs the gateway key's Secret in both namespaces before
  its pods start (NEED-0032).

## Where this promise ends

A declared estimator cannot see what the worker sees. The reference worker's estimate for a
resumed assignment is lower than what its estimator yields, so such a step reserves more than the
worker needs. A coding agent's demand depends on the task, and its fixed estimator is as rough as
its answer was before; calibration, not the estimator, narrows the error. W-02 checks an estimator
against the worker's answer for the suite's own request only, so an estimator that yields less for
another request is not caught there; the worker's rejection (W-10) then shows it after admission.

The capabilities still need one probe per adapter and process life. A daemon restarted starts it
again, and a worker whose capabilities change while the daemon runs is not asked again until the
next start.

A token stays valid until its job's deadline and a minute more, even when the job ended earlier.
A unit that leaked its token before it ended lets whoever holds it reach that job's hosts until
then, and nothing else. The gateway does not revoke a token. A rotated key takes effect at the
next request; tokens signed with the old key are refused from then on, so a rotation while jobs
run cuts their egress.

The container gateway is one process for every job of its key. When it fails, every running job
of that key loses its egress and the control plane's path to it, and those steps fail; the next
launch starts a new gateway. In the cluster the chart runs two replicas behind one Service, so
one replica's failure costs only the connections it held. A gateway connects only on the ports
the network policy allows, and it sees a host's name in a `CONNECT`, not the traffic inside.
