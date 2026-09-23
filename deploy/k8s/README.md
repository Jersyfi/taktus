# Deploying Taktus on Kubernetes

**This is the specification for the pull request that builds it, not the thing itself.** Nothing
under `deploy/k8s/` renders yet. The plan below says what that pull request must produce, and
why each part is there; it was written on 2026-09-23 against a cluster that was inspected
read-only, and against the target decision DEC-0023.

**No deployment's own names are in this file.** No address, no hostname, no namespace name a
particular cluster uses, no figure measured on one machine. The repository holds the
requirements and the values *keys*; the operator holds the values and the names, in their own
private place (`CREDENTIALS.md`: a deployment's name for a secret is that deployment's
business). Where a requirement depends on something only a cluster can tell you, the
requirement says which needs request asks for it.

---

## 1. The shape

Two namespaces, and the boundary between them is the point.

| Namespace | What runs there | Who may write in it |
|---|---|---|
| **the control plane's** | `taktusd` in its roles (`api`, `runner`, `scheduler`, `automation`), the database if it is deployed with Taktus, the ingress object | the deployment identity (CI or a person with `helm`) |
| **the execution namespace** | one Job per execution unit, and nothing permanent | Taktus's own service account, and only to create jobs and read their logs |

Nothing else. A third namespace holds whatever else the cluster runs; Taktus neither
administers the cluster nor reaches into it (ADR-0025 §1, DEC-0023).

**Two identities, kept apart, and this is the part that is easy to get wrong.**

- **The deployment identity** installs Taktus: it may create and change deployments,
  services, secrets, config maps and volume claims *in the control plane's namespace*. It
  belongs to CI or to the person running `helm`. It is **never** given to Taktus.
- **Taktus's own service account** runs the control plane. In the execution namespace it may
  `create`, `get`, `list`, `watch` and `delete` `batch/jobs`, and `get` and `list` `pods` and
  `pods/log`. Nothing else, anywhere: no shell, no node access, no secrets it did not mount,
  no read of another namespace, and no permission over the cluster's own objects. It is a
  namespaced Role and a RoleBinding, never a ClusterRole.

The reason for the split is ADR-0025: an instance must not administer the infrastructure it
runs on. A service account that could change its own deployment would be administering it.

## 2. The chart

One chart, `deploy/k8s/chart/`, that renders both namespaces. The values keys below are the
interface; their *values* are the operator's.

```
image:
  repository:            # where the control plane image is pulled from
  tag:                   # the released version, never `latest`
  pullPolicy:            # IfNotPresent
  pullSecret:            # name of an existing pull secret; empty when the image is public

roles:                   # one deployment per role (ADR-0002)
  api:        { replicas:, resources: { requests: {cpu:, memory:}, limits: {memory:} } }
  runner:     { replicas:, resources: {...} }
  scheduler:  { replicas: 1, resources: {...} }   # elected; more than one is allowed and idle
  automation: { replicas:, resources: {...} }

database:
  deploy:                # true: a StatefulSet in this namespace; false: an existing server
  storageClass:
  size:
  urlSecret:             # name of the Secret holding the connection URL
  urlKey:                # the key inside it; mounted as a file, read through TAKTUS_DATABASE_URL_FILE

execution:
  namespace:             # the execution namespace's name
  serviceAccount:        # the account jobs run as — not Taktus's own
  image:                 # the execution unit's image (the worker), by reference
  defaults: { cpu:, memory:, wallSeconds:, startTimeoutSeconds: }
  egress:
    proxyImage:          # the per-job egress proxy (section 6)
    enforce:             # true; false refuses to start a job whose frame names hosts

credentials:             # one entry per parameter of CREDENTIALS.md the instance needs
  - parameter:           # e.g. credential.model_api_key
    secret:              # the Secret's name in this cluster
    key:                 # the key inside it
    mountPath:           # where it is mounted; the variable TAKTUS_<KEY>_FILE points here

ingress:
  enabled:
  className:
  host:                  # the public name; the webhook arrives at <host><pathPrefix>/intake/<channel>
  pathPrefix:            # TAKTUS_PATH_PREFIX when Taktus is served under a sub-path
  tls: { secretName:, issuer:, issuerKind: }   # cert-manager, or an existing secret

telemetry:
  otlp: { endpoint:, protocol:, headersSecret:, headersKey: }   # all empty: spans stay local
```

**Every secret is mounted as a file and read through `TAKTUS_<KEY>_FILE`** — never handed to a
container as an environment variable, because variables leak into process listings and child
processes (`CREDENTIALS.md`). The chart's job is to mount them and set the `_FILE` variables;
it never carries a value, and a values file in the repository never carries one either.

**Migrations** run as a `Job` with a `helm.sh/hook: pre-upgrade,pre-install` and the control
plane's own image, `make migrate`. The instance does not migrate itself on start.

## 3. The image, and how it gets there

The repository's own CI builds and pushes the control plane image on a tag; a second image for
each worker that ships with the project (`workers/`), because the control plane image carries
no worker code (DEC-0011). Multi-stage build from `deploy/docker/Dockerfile`, which already
exists and is what `make up` uses.

- The registry is named only by the values key `image.repository`. Which registry, and whether
  the package is public, is the operator's.
- **Push-based, not pulled.** There is no GitOps controller in the target cluster, so the
  deployment is `helm upgrade --install` run by CI or by a person, with a kubeconfig for the
  deployment identity. If a GitOps controller is added later, the chart is what it watches and
  nothing in it changes.
- Taktus does not deploy itself (ADR-0013 D). The image a Taktus instance built is put into
  operation by another instance or by a person.

## 4. The execution namespace and its admission policy

The namespace carries the Pod Security labels:

```
pod-security.kubernetes.io/enforce: restricted
pod-security.kubernetes.io/audit:   restricted
pod-security.kubernetes.io/warn:    restricted
```

`restricted` is the point, not `baseline`: it is what forbids privilege escalation, running as
root, host namespaces, host paths and added capabilities, all of which a job that writes code
has no use for. Every job the adapter creates is written to satisfy it:
`runAsNonRoot: true`, `allowPrivilegeEscalation: false`, `capabilities: { drop: [ALL] }`,
`seccompProfile: { type: RuntimeDefault }`, and a read-only root filesystem with a writable
`emptyDir` for the workspace.

**No service-account token is mounted into a job**: `automountServiceAccountToken: false` on
the job's pod spec *and* on the service account it runs as. A unit that writes code has no
business holding a credential for the API server that runs it. This is the single most
valuable line in the whole plan.

**Every job carries limits and a deadline**, from the frame the assignment names and the
chart's defaults where it does not: `resources.requests` and `resources.limits` for CPU and
memory, `activeDeadlineSeconds` from the frame's wall clock, `backoffLimit: 0` — the run
retries a step, the cluster does not retry a job behind the run's back — and
`ttlSecondsAfterFinished` so that finished jobs are collected. A job without a limit is how one
runaway assignment takes the node down, and the node has no swap.

The adapter **refuses** a job it cannot give a limit to, exactly as the execution port already
refuses an unisolated unit above autonomy level 2.

## 5. Network policy: default-deny, both ways

In the execution namespace, one policy selecting every pod, with `policyTypes: [Ingress,
Egress]` and no rules at all — nothing in, nothing out. Then exactly the exceptions a job
needs:

- **Ingress:** from the control plane's namespace only, to the unit's contract port, selected
  by a namespace label. Nothing else may reach a job, and no job may reach another job.
- **Egress:** to the per-job egress proxy (section 6), and to nothing else. Not to the
  cluster's DNS — with a proxy the job does not resolve names itself — not to the API server,
  not to the node, not to the link-local metadata address, not to the control plane's database.

In the control plane's namespace, the same default-deny, with egress to its database, to the
execution namespace's API-server-mediated job creation, to the hosts its connectors and models
need, and to the OTLP collector when one is configured.

Both policies are in the chart, and both are rendered whether or not the cluster enforces
them — see the next section for what happens when it does not.

## 6. Egress: a host list is not a network policy

**`frame.allowed_hosts` names hostnames. A NetworkPolicy filters addresses. One cannot express
the other, and pretending otherwise is the dangerous part.** A hostname resolves to addresses
that change, several names share an address, and a policy written from today's resolution is
wrong tomorrow and too wide today.

So the host list is **not** enforced by the network policy. It is enforced the way the
container adapter already enforces it: by an **egress proxy of its own per job**, which sees
the hostname in the client's `CONNECT` and refuses every name that is not in the frame's list.
On Kubernetes it is a second pod, not a sidecar in the job's pod: containers in one pod share a
network namespace, so a sidecar can be walked around and is a boundary only in a diagram. With
a second pod, the job's default-deny egress policy permits exactly one destination — the proxy
— and the only way out is through it.

What that gives, plainly:

- A name not in the list is refused at the proxy, by name.
- A connection to a bare address is refused too: it is not a name in the list, and the policy
  would not have let it past the proxy anyway.
- The proxy sees the `CONNECT` host, not the traffic: TLS stays end to end between the job and
  the host it was allowed to reach.

**What the network policy still earns:** it is what makes the proxy unavoidable. Without it the
job could ignore `HTTPS_PROXY` and dial out directly. Policy and proxy are two halves of one
mechanism; neither is the mechanism.

**If a cluster cannot enforce a NetworkPolicy at all**, the mechanism has no second half and
the host list means nothing more than a line in a bundle. Then the adapter **refuses to start a
job whose frame names allowed hosts**, and says so with the reason — it does not start the job
with an unenforced list. `execution.egress.enforce: false` is the operator's explicit,
recorded choice to run without it, and the run's ledger records that the frame was not
enforced. **The one thing that must never happen is the list quietly meaning nothing.**

On the target cluster the enforcement is present: the NetworkPolicy controller is active and a
policy in another namespace already works. Verified read-only on 2026-09-23; the verification
and the cluster's own details are in the operator's private note, not here.

## 7. The cluster execution adapter

`src/taktus/adapters/driven/execution/kubernetes.py`, a third implementation of the execution
port beside `process` and `container`, with `Isolation.CLUSTER`. It:

1. creates one `Job` per execution unit, in the execution namespace, from the frame: the image,
   the resource limits, the deadline, the credentials as mounted files from Secrets it creates
   for the job's lifetime, and the environment the contract names (`TAKTUS_UNIT_PORT`,
   `TAKTUS_UNIT_STATE_DIR`);
2. creates the egress proxy pod and its Service with the frame's host list, and waits for both
   to be ready within `startTimeoutSeconds`;
3. reaches the unit at its Service address and speaks the worker contract to it, exactly as the
   other two adapters do — the port's interface does not change;
4. reads the job's logs for the unit's own log lines, and deletes the job, its Secrets and the
   proxy when the assignment ends, whatever the outcome;
5. refuses, with the port's `Refusal`, a job it cannot give limits to, a frame whose hosts it
   cannot enforce, and — as the port already does — an isolation that does not suffice for the
   run's autonomy level.

It is held to the same tests as the container adapter, including the one that checks from
inside the job that no credential is on a filesystem, in a recorded configuration or in a log.
A cluster is needed to run them; they skip with the reason where there is none, and CI says so
rather than passing quietly.

## 8. What the deployment still needs from the operator

Each of these is a needs request in `docs/decisions/`, because none of it is a session's to
create:

- **A kubeconfig for the deployment identity** — a service account with the Role of section 1,
  its token and the cluster's CA. Where the API server is reachable from outside, this replaces
  shell access entirely, which is the better arrangement: the deployment needs no account on the
  machine.
- **A public name for the ingress**, and the TLS arrangement behind it.
- **The webhook signing secret**, once the ingress name exists: it is set at the hosting
  service and in the instance in one move, and the connector refuses every delivery it cannot
  verify.
- **The database decision**: deployed with Taktus, or an existing server. ADR-0020 says one
  database per instance either way.

## 9. What this plan does not cover

- **Several nodes.** A node-local storage class binds a volume to one node. On one node that is
  invisible; the day there is a second, the database's volume is a migration.
- **A kernel boundary between the control plane and execution.** Deliberately not here
  (DEC-0023), and the three situations that would bring it back are named in that record.
- **Autoscaling and load.** The scaling claims of ADR-0002 are proven for two daemons on one
  database, not for a cluster under load.
- **Backups.** A database deployed by this chart has no backup in it. That is its own pull
  request and its own needs request, and ADR-0013 C — a manual restore path, documented and
  exercised — is not satisfied by a volume snapshot nobody has restored.
