# Deploying Taktus on Kubernetes

**The chart, the cluster execution adapter and the install are built.** This file was
written on 2026-09-23 as the specification, against a cluster that was inspected read-only and
against the target decision DEC-0023. Since #64 the chart under `chart/` renders what sections 1
to 6 require, and a release tag builds the images (section 3). Section 10 says what is built and
what still waits.

```bash
make helm                                            # the pinned helm, into .tools/bin
.tools/bin/helm lint deploy/k8s/chart --strict -f deploy/k8s/values.example.yaml
.tools/bin/helm template taktus deploy/k8s/chart --namespace <control plane namespace> -f <your values>
```

`values.example.yaml` is an example of the operator's values, used by the tests; every name in it
is an example. The operator's own values file lives in their private place.

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
| **the control plane's** | `taktusd` in its roles (`api`, `runner`, `scheduler`, `automation`), the database if it is deployed with Taktus, the ingress object | the deployment identity (a person with `helm`; CI never deploys) |
| **the execution namespace** | one Job per execution unit with what it lives with — its Secret and its Service — and the instance's egress gateway (section 6), which the chart deploys | Taktus's own service account, and only for those objects and the jobs' logs |

Nothing else. A third namespace holds whatever else the cluster runs; Taktus neither
administers the cluster nor reaches into it (ADR-0025 §1, DEC-0023).

**Two identities, kept apart, and this is the part that is easy to get wrong.**

- **The deployment identity** installs Taktus. In the two namespaces, and nowhere else, it may
  create, change and delete secrets, config maps, services, service accounts, volume claims,
  deployments, stateful sets, jobs, roles, role bindings, network policies and ingresses — in
  the control plane's namespace cron jobs too, for the backup (section 11) — and
  read pods, their logs and events. It may not create a namespace or any object of the cluster
  as a whole (NEED-0007). It belongs to the person running `helm`. It is **never** given to
  Taktus. The chart renders no kind outside that list, and a test holds it to that.
- **Taktus's own service account** runs the control plane. In the execution namespace it may:

  | Resource | Verbs | What for (§7) |
  |---|---|---|
  | `batch/jobs` | `create`, `get`, `list`, `watch`, `delete` | the unit's Job |
  | `pods`, `pods/log` | `get`, `list` | whether a job's pod is ready and how it ended; the unit's log lines |
  | `secrets` | `create`, `delete` | the credentials a job names, for the job's lifetime |
  | `services` | `create`, `get`, `delete` | the address the control plane reaches the unit at; `get` reads the address of the egress gateway's Service (section 6) |

  Nothing else, anywhere: no shell (`pods/exec`), no port forwarding, no node access, no read of
  a Secret — it can write a job's credentials into the namespace and can never read one back —
  no read of another namespace, and no permission over the cluster's own objects. It cannot
  create a pod directly, and it creates no Deployment: the egress gateway is the chart's. It is a namespaced Role and a
  RoleBinding, never a ClusterRole. `src/taktus/adapters/driven/execution/kubernetes/api.py`
  holds the same list as `PERMITTED`, and the client refuses every other call before sending
  it (DEC-0061).

  Creating a Secret includes creating one of the type that asks the cluster for a token of a
  service account in that namespace. Therefore no service account in the execution namespace
  holds any Role, the one jobs run as included: a token for it opens nothing.
  Taktus's token is mounted into the runner's pods alone, the role that creates jobs;
  every other pod runs without one.

The reason for the split is ADR-0025: an instance must not administer the infrastructure it
runs on. A service account that could change its own deployment would be administering it.

## 2. The chart

One chart, `deploy/k8s/chart/`. Its interface is `chart/values.yaml`: every key with its default
and a comment that says what it is for. The keys are the repository's; their *values* are the
operator's. The parts that carry a decision:

| Keys | What they decide |
|---|---|
| `namespaces.create` | `false` by default: both namespaces exist before the install, created by whoever may create namespaces, with the labels of section 4. The control plane renders into the release's namespace (`helm --namespace`), the execution units' objects into `execution.namespace`. `true` renders both Namespace objects with those labels, for a cluster where the installing identity may (DEC-0060) |
| `image.repository`, `image.tag`, `image.pullSecret` | the control plane image; the tag is a version, and `latest` or an empty tag fails the render |
| `profile` | `standard` (default): one deployment per role. `small`: one deployment running every role in one process (`TAKTUS_ROLES=all`), sized by `small.resources`, beside the database. See "Which profile" below |
| `roles.<role>.replicas`, `.resources` | one deployment per role (ADR-0002), for the `standard` profile; the scheduler is elected, more than one is allowed and idle |
| `database.deploy`, `.size`, `.storageClass`, `.passwordSecret`/`.passwordKey`, `.urlSecret`/`.urlKey` | a PostgreSQL of its own (DEC-0032) on a volume of 20 Gi (DEC-0033); its password and the instance's connection URL are existing Secrets |
| `state.size`, `.storageClass` | one volume for artifact bytes, shared by every role (`TAKTUS_STATE_DIR`); kept on uninstall. A role keeps at most `TAKTUS_OBJECT_CACHE_MB` of them in memory (default 64; set through `env`) |
| `execution.*` | `kind` (`cluster` for the cluster adapter of section 7, `endpoint` by default), the execution namespace, the jobs' account, the unit's image, the per-job defaults (`defaults.cpuRequestShare` the share of the CPU limit a unit requests, section 7; `defaults.serviceHosts` the hosts a worker's own service needs, section 6; `defaults.unitEnv` the variables a worker's own program needs to start, section 7 — configuration, never a secret), the claim the units' state lives on (`stateClaim`, rendered and kept on uninstall), the egress gateway (`gateway.replicas`, and optionally `gateway.keySecret` with `gateway.keyKey`, an existing Secret in both namespaces that holds its key; without them the chart makes the key and keeps it; section 6), and the egress port, allowed ports and excluded ranges, with `egress.proxyImage` the container adapter's gateway image. `workers[]` names several workers in the order a step is resolved in (`TAKTUS_WORKERS`, ADR-0078): each entry a `name` and what it sets itself — `kind`, `endpoint` (required for kind `endpoint`), `image`, `unitPort`, `cpus`, `cpuRequestShare`, `memoryMb`, `wallSeconds`, `startTimeoutSeconds`, an existing `stateClaim`, `serviceHosts` (`[]` for none), `unitEnv` (`{}` for none) — and the settings above for the rest. A name that is not lowercase words joined by hyphens, a name twice, or an endpoint worker without its endpoint fails the render |
| `credentials[]` | one entry per parameter of `CREDENTIALS.md`: `parameter`, `secret`, `key`, optional `mountPath`; mounted as a file, its path in `TAKTUS_<PARAMETER>_FILE`. A credential of one of several workers has the parameter `worker.<worker>.credential.<name>`, and only that worker receives it |
| `administration.platform`, `.administers` | the platform this instance runs on and, per credential parameter, the platforms it administers or `none` — `TAKTUS_PLATFORM`, `TAKTUS_ADMINISTERS` (ADR-0052). A process naming a credential that administers this platform, or one declared about nothing, is refused; with no platform nothing is checked |
| `connectors.repository.*` | the repository channel's connector as a deployment of its own, from the control plane's image, acting as Taktus's own app (ADR-0033): the repository it serves, the app's identifier, the Secrets holding the app's key and the webhook secret — mounted as files — and `findings`, which makes it the connector product findings go through. Enabled, it sets `TAKTUS_CONNECTORS` (`channel.repo`) and, with `findings`, `TAKTUS_FINDINGS_CONNECTOR`; it is reached from the roles alone and reaches the name service and the service's API outside the cluster (#66) |
| `connectors.chat.*` | the chat channel's connector as a deployment of its own, from the control plane's image, as Taktus's own app in the owner's chat workspace (NEED-0018): the Secret holding its bot token and signing secret, mounted as files. Enabled, it adds `channel.chat` to `TAKTUS_CONNECTORS`; it is reached from the roles alone and reaches the name service and the chat service's API outside the cluster (#239) |
| `ingress.*` | off unless `host` is given; `tls.secretName` names an existing certificate Secret, and then nothing is requested; only without it does `tls.issuer` ask the platform's certificate manager, by an annotation on the ingress. The stream of changes, `/changes`, is a long-lived `text/event-stream` response (ADR-0055): an ingress controller that buffers responses holds every change back until its buffer fills, and one that closes idle connections sooner than 15 seconds ends streams between heartbeats. Taktus sends `X-Accel-Buffering: no`; a controller that ignores it is told through `ingress.annotations`. Taktus cannot detect either |
| `backup.*` | the database's scheduled backup (section 11, ADR-0087): off unless `enabled`; the backup image, released with the instance; the `schedule`, daily by default; `retentionDays`, 30 by default (DEC-0058); `recipient`, an `age` public key, empty for no encryption; the store's `endpoint`, `region`, `bucket`, `prefix`, and the Secret holding its credential with the key of its identifier and of its secret, mounted as files. It reaches the name service, the database and the store on `egressPorts` outside the excluded ranges; the database admits it |
| `networkPolicy.*` | the name service, the API server's addresses, the ingress controller's namespace, and further egress rules for the hosts the control plane needs (section 5) |
| `telemetry.otlp.*`, `model.*`, `capacity.*` | as their `TAKTUS_*` variables; `model.outputCap` is `soft` by default, the setting's own default. An endpoint shown to hold the output limit — run M-03 against it — is set to `hard` in the operator's values. The Taktus project's own instance sets `hard`: M-03 passed against its endpoint on 2026-10-01 (research [A4]). That is its operator's value, not the chart's (ADR-0092); `model.usageKinds` the price kinds the endpoint reports, empty for `input,output` — M-04 holds the endpoint to it |
| `env` | further non-secret `TAKTUS_*` settings — tenants, connectors; a `_FILE` variable here fails the render, because a secret goes through `credentials` |
| `configFiles` | files of configuration a setting names by path, file name to content, mounted read-only at `/etc/taktus/files/<name>` in every role; the setting that reads one is set in `env`. A name that is not letters, digits, dots, hyphens and underscores fails the render. Never a secret. Empty by default |

**What one tenant measured or shaped is its operator's value, never the chart's** (ADR-0092).
The Taktus project's own instance is an example. Its operator's private values set:

| Values | What they carry |
|---|---|
| `model.outputCap: hard` | M-03 passed against the project's endpoint on 2026-10-01 |
| `configFiles.budget-seeds.yaml` from `docs/runs/first-run.seeds.yaml`, `env.TAKTUS_BUDGET_SEEDS: /etc/taktus/files/budget-seeds.yaml` | the calibration seed of the project's first live run |
| `configFiles.finding-form.md` from `.github/finding-form.md`, `env.TAKTUS_FINDINGS_FORM: /etc/taktus/files/finding-form.md`, `env.TAKTUS_FINDINGS_LABELS: task` | the shape of the project's issue form `Task`, for findings sent with `connectors.repository.findings` |
| `env.TAKTUS_CHANGE_PROCESS: s07-change-in-dialogue` | the project's process that turns a change in words into a proposal |
| `env.TAKTUS_FINDINGS_LEVEL: automatic`, `env.TAKTUS_FINDINGS_INTAKE_TENANT: <the project's tenant>` | the project's own findings keep leaving on their own, and its intake takes the findings other instances submit (ADR-0118, NEED-0033). The ingress routes `<prefix>/findings/intake` with the rest of the API; nothing else opens |

`helm --set-file configFiles.budget-seeds\.yaml=docs/runs/first-run.seeds.yaml` reads a file
into the values. `taktusctl guides` is told the project's manifest with
`--manifest docs/guides/guides.yaml` or `TAKTUS_GUIDES_MANIFEST`.

**Every secret is mounted as a file and read through `TAKTUS_<KEY>_FILE`** — never handed to a
container as an environment variable, because variables leak into process listings and child
processes (`CREDENTIALS.md`). The chart's job is to mount them and set the `_FILE` variables;
it never carries a value, and a values file in the repository never carries one either. **The
chart creates no Secret**: every Secret it names exists before the install — the database's
password and URL, the webhook secret, the backup store's credential, the repository app's key,
the certificate. The operator creates them, and the deployment identity may (section 1).

**The database is the instance's own** (DEC-0032): the chart deploys a PostgreSQL with the
instance, and no other system uses that server, because a shared database means the system meant
to report a failure fails with it. It sits in the instance's own namespace, the control plane's — confirmed by the owner on
2026-10-01.

**Storage is sized once and watched from the first day.** The database's volume defaults to
20 Gi (`database.size`, DEC-0033). On the target's storage class a volume cannot be enlarged
after it was created, and the ledger only grows. The chart therefore sets
`TAKTUS_CAPACITY_DATABASE_VOLUME_MB` from `database.size` and
`TAKTUS_CAPACITY_STORAGE_EXPANDABLE` from the storage class's `allowVolumeExpansion` — false on
the target — so that the instance holds the database's own size, which it measures, against a
volume it cannot see. From the first run the scheduler reports every hour: the growth per run
(the database's size over the runs it holds, an upper bound), runs per day, the date the volume
is full and the date it falls below 10 % free. Thirty days before that date the finding turns to
*act*, is logged as a warning and recorded in the ledger as `capacity.storage.database`
(ADR-0031, `docs/architecture/platform.md`). The migration to a larger volume is the operator's,
and it needs those thirty days. Every job's pod carries `resources.limits.memory` equal to its
unit's limit, because the node has no swap: a job without one is refused, not started.

**Migrations** run as a `Job` with the control plane's own image and the command `make migrate`
runs (`alembic -c migrations/alembic.ini upgrade head`). The instance does not migrate itself on
start. Every upgrade migrates before the new version starts (`pre-upgrade`). The first install
migrates before anything starts when the database exists already (`database.deploy: false`,
`pre-install`). When the chart deploys the database, the first install migrates right after
creating it (`post-install`), because a hook that runs before the install has no database to
migrate (DEC-0060). An upgrade that changes only the release's image does not restart the
database: its pod template carries no label that changes with a release (#237). Until it is done the roles refuse to start against an empty schema and are
restarted.

**Tenants are created after the install, not configured** (ADR-0104). The migration creates
`default`. Every other tenant is created with `taktusctl tenant create NAME`, run in a pod of
the control plane, which prints the identifier Taktus generated. Every role serves the new
tenant at its next round, without a restart. The chart sets no `TAKTUS_TENANTS` and mounts no
administration key, so the administration of tenants on the HTTP surface stays off on a
cluster.

**Every pod runs under the restricted profile**, the database included: not as root, no
privilege escalation, every capability dropped, the runtime's default seccomp profile and a
read-only root filesystem. The control plane's namespace can therefore enforce `restricted` too.

### Which profile

| Profile | Suits | Costs |
|---|---|---|
| `small` | one team or a trial on a cluster; the smallest footprint: the control plane in one pod, plus the database | not highly available: a restart of the pod stops every role until it is back, resuming at the last step boundary. The pod holds Taktus's service-account token, as the runner does. Roles cannot be scaled apart |
| `standard` | an instance that needs roles scaled or restarted apart | one pod per role |

Neither is the highly available profile (#342). For one machine, Docker Compose remains the
way; the chart is for a cluster.

## 3. The image, and how it gets there

The repository's own CI builds and pushes the control plane image on a tag; a second image for
each worker that ships with the project (`workers/`), because the control plane image carries
no worker code (DEC-0011). Multi-stage build from `deploy/docker/Dockerfile`, which already
exists and is what `make up` uses.

- `.github/workflows/images.yml` runs on a tag `v<version>` and on nothing else. It builds
  `taktus`, `taktus-worker-script` and `taktus-worker-coding`, tags each with the version and
  pushes them to the registry the repository variable `IMAGE_REGISTRY` names. Without the
  variable it builds nothing, pushes nothing and says so. It has no deploy step, and a test
  holds it to all three. The variable, and a push credential where the registry is not the
  repository service's own, are NEED-0014.
- The registry is named only by the values key `image.repository`. Which registry, and whether
  the package is public, is the operator's.
- **Push-based, not pulled.** There is no GitOps controller in the target cluster, so the
  deployment is `helm upgrade --install` run by CI or by a person, with a kubeconfig for the
  deployment identity. If a GitOps controller is added later, the chart is what it watches and
  nothing in it changes.
- Taktus does not deploy itself (ADR-0013 D). The image a Taktus instance built is put into
  operation by another instance or by a person.

## 4. The execution namespace and its admission policy

The namespace carries the Pod Security labels. **They are set where the namespace is created**,
outside the chart, because the deployment identity may not create or change a namespace; the
chart sets them only when it renders the namespaces itself (`namespaces.create: true`):

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
- **Egress:** to the instance's egress gateway (section 6), and to nothing else. Not to the
  cluster's DNS — with a proxy the job does not resolve names itself — not to the API server,
  not to the node, not to the link-local metadata address, not to the control plane's database.

The adapter labels what it creates so that the policies can select it: every object carries
`taktus/job: <the job's tag>` and `taktus/role: unit`; the chart's egress gateway carries
`taktus/role: egress`. So the exceptions are: ingress to `taktus/role: unit` on the contract port
from the control plane's namespace; egress from `taktus/role: unit` to `taktus/role: egress` on
port 3128; ingress to `taktus/role: egress` on port 3128 from `taktus/role: unit`; and egress
from `taktus/role: egress` to the cluster's DNS and to addresses outside the cluster, because
the gateway resolves the names the frame lists and connects to them. A policy cannot tell one
job from another; the job's token at the gateway does that (section 6).

In the control plane's namespace, the same default-deny, with egress to its database, to the
execution namespace's API-server-mediated job creation, to the hosts its connectors and models
need, and to the OTLP collector when one is configured.

Both policies are in the chart, and both are rendered whether or not the cluster enforces
them — see the next section for what happens when it does not.

The chart renders these exceptions by those labels. The gateway may leave the cluster to the
ports in `execution.egress.ports` (443 by default), to any
address outside `execution.egress.exceptCidrs` — the private, shared and link-local ranges, so
neither the cluster's own networks nor the metadata address — and to the name service.

Some reaching-out the chart cannot know: the API server's addresses
(`networkPolicy.apiServer.cidrs`), the ingress controller's namespace
(`networkPolicy.ingressController.namespace`), and the hosts the control plane's connectors,
model and collector need (`networkPolicy.controlPlaneEgress`, as egress rules). A certificate
manager that proves a name over HTTP starts a challenge pod in the namespace of the certificate;
`networkPolicy.ingressController.alsoTo` names it by its labels, so that renewal is not refused
by the default-deny.

## 6. Egress: a host list is not a network policy

**`frame.allowed_hosts` names hostnames. A NetworkPolicy filters addresses. One cannot express
the other, and pretending otherwise is the dangerous part.** A hostname resolves to addresses
that change, several names share an address, and a policy written from today's resolution is
wrong tomorrow and too wide today.

So the host list is **not** enforced by the network policy. It is enforced the way the
container adapter enforces it: by the instance's **egress gateway** (ADR-0115), which sees the
hostname in the client's `CONNECT` and refuses every name that the job's token does not name.
It is a Deployment of its own in the execution namespace (`templates/gateway.yaml`, two
replicas behind the Service `<release>-gateway`), not a sidecar in the job's pod: containers in
one pod share a network namespace, so a sidecar can be walked around and is a boundary only in a
diagram. The job's default-deny egress policy permits exactly one destination — the gateway —
and the only way out is through it. One gateway serves every job; until ADR-0115 every job
brought a proxy of its own, a second Job with its own Service.

What that gives, plainly:

- A name not in the list is refused at the gateway, by name.
- A connection to a bare address is refused too: it is not a name in the list, and the policy
  would not have let it past the gateway anyway.
- The gateway sees the `CONNECT` host, not the traffic: TLS stays end to end between the job and
  the host it was allowed to reach.

**What the network policy still earns:** it is what makes the gateway unavoidable. Without it
the job could ignore `HTTPS_PROXY` and dial out directly. Policy and gateway are two halves of
one mechanism; neither is the mechanism.

**What the policy cannot do: tell one job from another.** The exceptions of section 5 select by
role, so every unit reaches the gateway. The gateway therefore asks each request for the job's
token, and admits the hosts that token names and nothing else. The runner mints the token per
job: the job's hosts and its deadline, signed with the gateway's key (HMAC-SHA256). It is held
in the job's Secret, and the unit finds it in its proxy address
(`http://taktus:<token>@<address>:3128`), which every common client turns into a
`Proxy-Authorization` header by itself. The gateway answers 407 to a request without a token its
key signed, or whose job's deadline has passed, and 403 to a host its token does not name. The
token is in no recorded configuration.

**The gateway's key** is a random value, in a Secret of the same name in **both** namespaces:
the gateway mounts it in the execution namespace, and the runner, which signs the tokens, in the
control plane's (`CREDENTIALS.md`, *Egress gateway key*). The chart makes it on the first install,
`<release>-gateway-key`, and writes the same value again at every upgrade, read back from the
control plane's namespace; nobody provides it (DEC-0216). An uninstall keeps both. An operator who
wants a key of their own names an existing Secret of the same name in both namespaces, with at
least 32 random bytes, in `execution.gateway.keySecret` and `keyKey`. Rotating it: write a new value into both Secrets and restart the gateway and the
runner; tokens signed with the old key are refused from then on, so a rotation while jobs run cuts
their egress.

**If a cluster cannot enforce a NetworkPolicy at all**, the mechanism has no second half and
the host list means nothing more than a line in a bundle. Then the adapter **refuses to start a
job whose frame names allowed hosts**, and says so with the reason — it does not start the job
with an unenforced list. `execution.egress.enforce: false` is the operator's explicit,
recorded choice to run without it, and the run's ledger records that the frame was not
enforced. **The one thing that must never happen is the list quietly meaning nothing.**

**A worker's own service is not in the frame.** A coding worker's agent calls its provider's
API to work at all; a model worker calls its model's. That host belongs to the worker, not to
the step: a bundle names what its step may reach, and must not have to name which provider
the operator chose. So the operator names it as configuration, per worker:
`execution.defaults.serviceHosts`, or `serviceHosts` of an entry of `execution.workers[]`
(`TAKTUS_EXECUTION_SERVICE_HOSTS`, ADR-0089). Each is a host name as the frame names one —
lowercase, optionally with a port, no wildcard — and is validated the same way at startup.

- **An assignment's job** gets the frame's hosts and the service hosts, each once, in its
  token. The frame handed to the worker is still the step's: the worker refuses a tool
  call to a service host the frame does not name (W-13). The service host is reachable by the
  agent, not granted to the step.
- **The conformance suite's unit** gets the suite's hosts (`conformance.worker.hosts`) and the
  service hosts, so that the suite exercises the worker as a run would.
- **A probe** — the unit started once to answer the capabilities — gets none, and no
  credential either. An estimate starts no unit at all: it is what the estimator the worker
  declares yields (ADR-0115).
- **Empty**, the default, changes nothing: a unit reaches the frame's hosts alone.

The gateway still connects only on `execution.egress.ports` and to no address in
`execution.egress.exceptCidrs`; a service host on another port needs that port there too.
With `execution.egress.enforce: false` a job that names hosts is refused, and service hosts
are hosts: a worker that names them cannot run on such a cluster at all.

On the target cluster the enforcement is present; it was verified read-only on 2026-09-23. The
verification and every detail of that cluster are in the operator's private note and not here,
because this repository is public (`CREDENTIALS.md`).

## 7. The cluster execution adapter

`src/taktus/adapters/driven/execution/kubernetes/`, a third implementation of the execution
port beside `process` and `container`, with `Isolation.CLUSTER`, selected by
`TAKTUS_EXECUTION=cluster` with `TAKTUS_EXECUTION_NAMESPACE`. It speaks to the cluster's API
with `httpx` alone, through the calls of the Role of section 1 and no other. It:

1. creates one `Job` per execution unit, in the execution namespace, from the frame: the image;
   a memory request equal to the memory limit, and a CPU request of a share of the CPU limit
   (below); `activeDeadlineSeconds` of the wall clock plus
   the start timeout, as the cluster's backstop; `backoffLimit: 0`; `ttlSecondsAfterFinished`;
   a pod that satisfies `restricted` (section 4) and mounts no service-account token; the
   environment the contract names (`TAKTUS_UNIT_PORT`, `TAKTUS_UNIT_STATE_DIR`); the variables
   the worker's configuration names (below); and the
   credentials from a Secret it creates for the job — a `file` credential mounted from a key at
   its exact path, an `env` credential as a variable from a key, because the worker contract
   asks for it there, as the container adapter does. The pod's recorded configuration names the
   Secret's keys and never a value;
2. when the job names hosts — the frame's, and for an assignment the worker's service hosts
   (section 6) — reads the address of the egress gateway's Service
   (`TAKTUS_EXECUTION_GATEWAY_SERVICE`) and puts into the job's Secret the gateway's address with
   a token that names those hosts. Without hosts there is no token, and the job reaches nothing;
3. reaches the unit at its Service's address and speaks the worker contract to it, exactly as
   the other two adapters do — the port's interface does not change. The unit must answer
   health within `startTimeoutSeconds`; when it does not, the error says what the cluster says
   about the pod (an image that cannot be pulled, a pod that cannot be scheduled);
4. ends a job that exceeds the wall clock by deleting it, keeps the unit's log lines under the
   control plane's state directory, and deletes the job, its Secret and its Service when the
   assignment ends, whatever the outcome. Every one of them is owned by the unit's Job,
   so that the cluster removes them too when the control plane died before it could: the
   deadline ends the Job, its time to live deletes it, and what it owns goes with it;
5. refuses, with the port's `ExecutionRefused` and before creating anything, a job it cannot
   give limits to, a job that names a credential under the name of one of the unit's variables, a job that names hosts while `execution.egress.enforce` is false, and an
   isolation that does not suffice for the run's autonomy level. With network policies not
   enforced, a pod's network is open: the cluster then isolates the process and the filesystem,
   not the reach, and every job at level 3 or above — or at a level not known — is refused,
   as ADR-0002 refuses an unisolated unit.

**CPU is shared; memory is not.** A request is what the cluster's scheduler reserves for a
pod on a node; a limit is what the pod may use. A unit requests
`execution.defaults.cpuRequestShare` of its CPU limit — a quarter by default
(`TAKTUS_EXECUTION_CPU_REQUEST_SHARE`, NTC-0190) — and its whole memory limit:

- **CPU is compressible.** A unit that wants more CPU than the node has free is slowed down, not
  stopped. Units mostly wait — for a model, for the network — so a request of the whole limit
  keeps cores reserved that nobody uses, and a second unit waits for CPU on a node whose cores
  are mostly idle (#244). With a share, more units fit; each may still use up to its limit while
  the node has CPU to spare. When the node is busy, each container gets CPU in proportion to what
  it requested, and a unit's work takes longer. Its wall clock does not stretch with it.
- **Memory is not compressible.** A container over its memory limit is killed, and the node has
  no swap. A memory request below the limit would let the scheduler place units whose memory
  together exceeds the node's, and a unit could be killed for memory another pod took. The
  memory request therefore stays the memory limit, and memory is what decides how many units
  fit on a node.

A share of 1 requests the whole limit, as before #244. A worker of `execution.workers[]` may set
its own `cpuRequestShare`. A unit whose CPU request is below its limit leaves the cluster's
highest quality-of-service class, *Guaranteed*, for *Burstable*. When the node itself runs out
of memory — because other pods use more than they requested — the kernel then picks such a unit
sooner than a *Guaranteed* pod. Its memory request equal to its limit still keeps it out of the
first rank the node evicts for memory: the pods using more memory than they requested. The
egress gateway's pods request their memory limit too.

Admission does not count a unit's CPU, from its limit or its request. Admission against the
platform (ADR-0031) holds memory alone, and only for units started on the platform the control
plane runs on; a Job in the cluster is placed by the cluster's scheduler, outside what that
platform observes. Admission at a worker's capacity (ADR-0037) counts assignments, not cores.
The share therefore changes where the cluster places units, and nothing Taktus admits.

**A unit receives the variables its worker's configuration names.** The adapter starts the
image's own command, so a worker that needs a setting to start reads it from its environment —
the coding worker needs `CODING_AGENT_AUTH` and exits without it. The operator names them as a
map: `execution.defaults.unitEnv`, or `unitEnv` of an entry of `execution.workers[]`, which
replaces the default for that worker (`TAKTUS_EXECUTION_UNIT_ENV`, ADR-0090). Every unit of the
worker gets them as plain values in its pod — an assignment's, a probe's and the conformance
suite's. **They are configuration, visible in the ConfigMap, the startup log and every pod's
description, and never a secret.** A name that carries one stops the daemon's start: the
`TAKTUS_` namespace, a name ending in `_FILE`, a name the adapter sets itself (`HOME`,
`TMPDIR`, the proxy variables), a name with the word `TOKEN`, `KEY`, `SECRET`, `PASSWORD` or
`PASSWD`, and a credential the worker is configured with. The rule reads names only: a secret
given under another name is not recognised, and the operator answers for what a value holds. A
secret is a credential under `credentials`. A value with a comma fails the render.

The unit's state lives on the volume claim `execution.stateClaim` names, which the chart
renders; without one it is an empty directory that dies with the job, and the adapter's
startup log says so.

With several workers (`execution.workers[]`), each worker's jobs are created by the same adapter
in the same namespace, with that worker's image and limits and only that worker's credentials.
They share the claim of `execution.stateClaim` unless a worker names an existing claim of its
own.

It is held to the container adapter's tests (`tests/adapters/execution/test_kubernetes_cluster.py`),
including the one that checks from inside the job that no credential is on a filesystem, in a
recorded configuration or in a log. A cluster is needed to run them, and none is configured in
CI (NEED-0015); they skip with the reason, which every test summary prints. A fake of the
cluster's API (`test_kubernetes.py`) always runs: what a frame becomes, what is refused, that
everything is deleted, and that no call leaves the Role.

## 8. What the deployment still needs from the operator

Each of these is a needs request in `docs/decisions/`, because none of it is a session's to
create. All but the last were provided on 2026-10-08; their outcomes are in the register, and
the names they gave are in the owner's private note.

- **A kubeconfig for the deployment identity** (NEED-0007): a namespaced account with the rights
  of section 1, its token and the cluster's certificate authority. The two namespaces were
  created with it, outside the chart, with their Pod Security labels.
- **A public name for the ingress** (NEED-0008), with its certificate as a Secret in the control
  plane's namespace, renewed by the platform's certificate manager: `ingress.host` and
  `ingress.tls.secretName`.
- **The webhook signing secret** (NEED-0010), a Secret in the control plane's namespace, named in
  `credentials`.
- **A backup destination off the node** (NEED-0009); see §9.
- **The database decision** — answered (DEC-0032): a PostgreSQL of its own, deployed with the
  instance; its volume 20 Gi (DEC-0033).
- **The registry the images are pushed to** (NEED-0014): the repository variable the image
  workflow reads, and a push credential where the registry is not the repository service's own.

## 9. What this plan does not cover

- **Several nodes.** A node-local storage class binds a volume to one node. On one node that is
  invisible; the day there is a second, the database's volume is a migration.
- **A kernel boundary between the control plane and execution.** Deliberately not here
  (DEC-0023), and the three situations that would bring it back are named in that record.
- **Autoscaling and load.** The scaling claims of ADR-0002 are proven for two daemons on one
  database, not for a cluster under load.
- **A backup of anything but the database and the object store.** The execution state claim is
  not backed up (section 11). Neither is the work of the hours since the last backup: the
  schedule is daily by default.

## 10. What is built, and what still waits

**Built** (#64): the chart, rendering sections 1, 2, 4 and 5 — both namespaces' objects, one
deployment per role, the database with its volume, the migrations, the two service accounts with
the Role, the default-deny policies both ways with their exceptions, the ingress; every secret a
mounted file. `helm lint` and `helm template` run in CI against `values.example.yaml`, and
`tests/governance/test_chart.py` reads the rendered manifests back. The image workflow of
section 3.

**Installed** (#66, 2026-10-11), from the chart and the images of `v0.2.0-rc.3`, by the
deployment identity: the four roles, the database, both connectors and the ingress under the
public name with its existing certificate; the cluster execution adapter (`execution.kind:
cluster`) runs every worker step. Shown on the platform: readiness and health on the public name;
the capacity report with the node's figures; a signed delivery from Taktus's app accepted and
answered as the app, an unsigned or wrongly signed one refused; the chat service's verification of
the chat intake; a job started by the instance in the execution namespace with its limits; and the
egress proxy refusing a host outside the unit's frame while the named host answered. On a first
install with `database.deploy: true` the roles start only after the post-install migration, so an
install that waits for readiness (`helm --wait`) never finishes: install without it and wait for
the migrations' job. A unit requested its whole CPU limit on the node then; on a small node a second
unit waited for CPU while most cores were idle. Since #244 a unit requests a share of its CPU
and all of its memory (section 7), so memory decides how many fit.

**Backed up** since 2026-10-12 (#67, NEED-0025): the chart's job runs on the instance, its first
backup is in the store and was restored from it on the workstation (`docs/runs/2026-10-11-the-first-restore.md`).
The backup holds the database and not the state volume's artifacts; that is #322.

**A pull request P-03 opened on the installed instance** (#66, DEC-0063), on 2026-10-13: #373,
authored by Taktus's own app, closing #278. The run cloned the repository through its unit's
egress proxy, implemented the issue with the coding agent in a cluster unit, put the change on
a branch through the connector, waited for the pipeline's verdict and opened the pull request.
Four findings on the way were fixed first, each in a release candidate: the proxy's 407 named no
scheme (#356), units the node had no room for failed their step (#358), a change of a workflow
file was refused (#366), and a branch write was reserved by another operation's error (#370).
The run is in `docs/runs/2026-10-13-the-instance-opens-its-own-pull-request.md`.

## 11. Backup and restore

The database is backed up by a CronJob of the chart, `backup.enabled` (ADR-0087). Each run dumps
the whole database with `pg_dump`, encrypts the dump to an `age` public key where `backup.recipient`
names one, writes it to the store off the node, and then deletes every backup older than
`backup.retentionDays` (30 by default, DEC-0058). The newest backup is never deleted, and an
object the backup did not write is never touched. A run whose backup failed deletes nothing; its
Job stays for its log.

A backup is up to three objects under one name, `taktus-<UTC time>`:

| Object | What it holds |
|---|---|
| `<name>.dump` (`.dump.age` encrypted) | the database, `pg_dump --format=custom` |
| `<name>.objects.tar.gz` (`.age` encrypted) | the object store: every artifact, block record and recording the database names by digest, archived after the dump. Written with `backup.objects`, the default (#322) |
| `<name>.json` (`.json.age` encrypted) | when, the dump's and the archive's SHA-256 and size, the archive's count of files, whether they are encrypted, the schema revision, and every tenant's ledger head — `seq` and `hash` of its last entry — read before the dump |

**What the backup needs.** The database URL the roles read (`database.urlSecret`), as a login
that reads every row: every tenant's table forces row-level security, so the login is the
database's superuser or holds `BYPASSRLS`. With `database.deploy: true` it is the superuser. The
store's credential, one Secret with two keys (`CREDENTIALS.md`). Where encryption is wanted, an
`age` key pair made by the operator off the instance (`age-keygen -o key.txt`): its public key
(`age1…`) goes into `backup.recipient`, the file with its private key into the operator's own
secret store. The instance never holds the private key, and cannot read its own backups. With
`backup.objects`, the state volume, mounted read-only. It is ReadWriteOnce, so the backup's pod
is scheduled onto the node of the control plane's pods, and does not start while none runs.

**Who hears of a failed or missing backup** (ADR-0106). Every run records its outcome in the
database it backed up: one row of `backup_outcome` per tenant, `ok` or `failed` with the step
that failed. The chart sets `TAKTUS_BACKUP_EXPECTED_HOURS` from `backup.expectedHours`, 26 by
default. While the scheduler leads, it tells each tenant's owner-facing channel of a failed run,
and of a last success older than that, once until a successful run clears it. A tenant without
a channel hears nothing; the daemon's startup log names it, and `taktusctl alerts` on the
instance shows what it would have heard. A login with `BYPASSRLS` that is not the superuser
needs `GRANT INSERT ON backup_outcome` for the recording; without it the backup still runs, and
is reported as missing.

**Run one now.** `kubectl create job --from=cronjob/<release>-backup <release>-backup-now` in the
control plane's namespace, then read its log.

### The restore, by hand

Nothing here needs Taktus. It needs `rclone` (or any client of the store), `age` where the backup
is encrypted, and `psql` and `pg_restore` of the database's major version — all four are in the
backup image, which may be run for the purpose. `tests/deploy/test_backup_restore.py` runs these
steps against a fresh database.

1. **Stop everything that writes.** Scale the four roles and the connectors to zero, or uninstall
   the release; the database volume stays (section 2).
2. **Choose the backup.** List the store with the store's credential (the variables are
   `rclone`'s own; the values come from the operator's secret store, never from a file in a
   repository):

   ```bash
   export RCLONE_S3_PROVIDER=Other RCLONE_S3_ENDPOINT=<endpoint> \
          RCLONE_S3_ACCESS_KEY_ID=<identifier> RCLONE_S3_SECRET_ACCESS_KEY=<secret>
   rclone --config /dev/null lsf :s3:<bucket>/<prefix>
   ```

   and copy the chosen backup's objects out:

   ```bash
   rclone --config /dev/null copyto :s3:<bucket>/<prefix>/<name>.dump ./<name>.dump
   rclone --config /dev/null copyto :s3:<bucket>/<prefix>/<name>.objects.tar.gz ./<name>.objects.tar.gz
   rclone --config /dev/null copyto :s3:<bucket>/<prefix>/<name>.json ./<name>.json
   ```

   Compare the dump's SHA-256 (`sha256sum <name>.dump`) with the manifest's `sha256`, and the
   archive's with the manifest's `objects.sha256`.
3. **Decrypt, where the names end in `.age`**, with the private key from the operator's secret
   store:

   ```bash
   age --decrypt --identity key.txt --output <name>.dump <name>.dump.age
   age --decrypt --identity key.txt --output <name>.objects.tar.gz <name>.objects.tar.gz.age
   age --decrypt --identity key.txt --output <name>.json <name>.json.age
   ```

   The manifest's `sha256` is that of the encrypted object.
4. **Prepare an empty database.** A new server, or the instance's own after its volume was
   replaced, with the login the instance will use. The application role is not in the dump,
   because roles belong to the server; create it and grant it to the login:

   ```bash
   psql --dbname "$URL" -v ON_ERROR_STOP=1 \
     -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'taktus_app') THEN CREATE ROLE taktus_app NOLOGIN; END IF; END \$\$" \
     -c "GRANT taktus_app TO CURRENT_USER"
   ```

   `$URL` is the database's URL without the password; the password goes into `PGPASSWORD`.
5. **Restore**, in one transaction, as that login:

   ```bash
   pg_restore --no-owner --exit-on-error --single-transaction --dbname "$URL" <name>.dump
   ```

6. **Restore the object store** into the state volume's `objects` directory, empty or not: a
   file of the archive is named by its content's digest, so one already there is the same.

   ```bash
   mkdir -p <state>/objects && tar -xzf <name>.objects.tar.gz -C <state>/objects
   ```

   `<state>` is the state volume (`<release>-state`) mounted by a pod of the operator's choice, or
   a new volume of that name. A backup without an archive restores the database alone: what its
   runs name by digest is not readable, and a halted run escalates on resume.
7. **Check every tenant's chain** against the manifest's heads. The heads, as the database now
   holds them, as the superuser:

   ```bash
   psql --dbname "$URL" --tuples-only --no-align -c "SELECT tenant, seq, hash FROM (SELECT DISTINCT ON (tenant) tenant, seq, hash FROM ledger_entry ORDER BY tenant, seq DESC) AS head ORDER BY tenant"
   ```

   Every tenant of the manifest must appear with the same `seq` and `hash`; a tenant may have
   more entries only if the dump was taken after the manifest's heads were read. Whether an
   entry was changed is the chain's own proof: the head's hash covers every entry before it.
   Taktus verifies a chain from its last verified checkpoint (ADR-0105), and the checkpoint is
   restored with the dump. After a restore, verify every tenant's whole chain from its first
   entry once: `taktusctl ledger verify --full --tenant <tenant>` for each.
8. **Start Taktus again** with the same chart values. The schema revision of the manifest must
   be one the released version migrates from; an older backup is migrated forward by the
   release's own migration Job.

The restore of an encrypted backup without its private key is impossible, by design. Keep the
key where a failure of the instance does not reach it.

