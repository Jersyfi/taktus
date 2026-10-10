# Deploying Taktus on Kubernetes

**The chart is built; the cluster execution adapter and the install are not.** This file was
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
| **the execution namespace** | one Job per execution unit with what it lives with — its Secret, its Services, its egress proxy — and nothing permanent | Taktus's own service account, and only for those objects and the jobs' logs |

Nothing else. A third namespace holds whatever else the cluster runs; Taktus neither
administers the cluster nor reaches into it (ADR-0025 §1, DEC-0023).

**Two identities, kept apart, and this is the part that is easy to get wrong.**

- **The deployment identity** installs Taktus. In the two namespaces, and nowhere else, it may
  create, change and delete secrets, config maps, services, service accounts, volume claims,
  deployments, stateful sets, jobs, roles, role bindings, network policies and ingresses, and
  read pods, their logs and events. It may not create a namespace or any object of the cluster
  as a whole (NEED-0007). It belongs to the person running `helm`. It is **never** given to
  Taktus. The chart renders no kind outside that list, and a test holds it to that.
- **Taktus's own service account** runs the control plane. In the execution namespace it may:

  | Resource | Verbs | What for (§7) |
  |---|---|---|
  | `batch/jobs` | `create`, `get`, `list`, `watch`, `delete` | the unit's Job, and the egress proxy's, which is a Job too |
  | `pods`, `pods/log` | `get`, `list` | whether a job's pod is ready and how it ended; the unit's log lines |
  | `secrets` | `create`, `delete` | the credentials a job names, for the job's lifetime |
  | `services` | `create`, `delete` | the address the control plane reaches the unit at, and the one the unit reaches its proxy at |

  Nothing else, anywhere: no shell (`pods/exec`), no port forwarding, no node access, no read of
  a Secret — it can write a job's credentials into the namespace and can never read one back —
  no read of another namespace, and no permission over the cluster's own objects. It cannot
  create a pod directly; the proxy runs as a Job for that reason. It is a namespaced Role and a
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
| `roles.<role>.replicas`, `.resources` | one deployment per role (ADR-0002); the scheduler is elected, more than one is allowed and idle |
| `database.deploy`, `.size`, `.storageClass`, `.passwordSecret`/`.passwordKey`, `.urlSecret`/`.urlKey` | a PostgreSQL of its own (DEC-0032) on a volume of 20 Gi (DEC-0033); its password and the instance's connection URL are existing Secrets |
| `state.size`, `.storageClass` | one volume for artifact bytes, shared by every role (`TAKTUS_STATE_DIR`); kept on uninstall |
| `execution.*` | `kind` (`cluster` for the cluster adapter of section 7, `endpoint` by default), the execution namespace, the jobs' account, the unit's image, the per-job defaults, the claim the units' state lives on (`stateClaim`, rendered and kept on uninstall), and the egress proxy's image, port, allowed ports and excluded ranges |
| `credentials[]` | one entry per parameter of `CREDENTIALS.md`: `parameter`, `secret`, `key`, optional `mountPath`; mounted as a file, its path in `TAKTUS_<PARAMETER>_FILE` |
| `administration.platform`, `.administers` | the platform this instance runs on and, per credential parameter, the platforms it administers or `none` — `TAKTUS_PLATFORM`, `TAKTUS_ADMINISTERS` (ADR-0052). A process naming a credential that administers this platform, or one declared about nothing, is refused; with no platform nothing is checked |
| `connectors.repository.*` | the repository channel's connector as a deployment of its own, from the control plane's image, acting as Taktus's own app (ADR-0033): the repository it serves, the app's identifier, the Secrets holding the app's key and the webhook secret — mounted as files — and `findings`, which makes it the connector product findings go through. Enabled, it sets `TAKTUS_CONNECTORS` (`channel.repo`) and, with `findings`, `TAKTUS_FINDINGS_CONNECTOR`; it is reached from the roles alone and reaches the name service and the service's API outside the cluster (#66) |
| `ingress.*` | off unless `host` is given; `tls.secretName` names an existing certificate Secret, and then nothing is requested; only without it does `tls.issuer` ask the platform's certificate manager, by an annotation on the ingress |
| `networkPolicy.*` | the name service, the API server's addresses, the ingress controller's namespace, and further egress rules for the hosts the control plane needs (section 5) |
| `telemetry.otlp.*`, `model.*`, `capacity.*` | as their `TAKTUS_*` variables; `model.outputCap: hard` because this tenant's endpoint holds the limit (research [A4]; M-03 passed against it on 2026-10-01) — for another endpoint, run M-03 and set what it shows |
| `env` | further non-secret `TAKTUS_*` settings — tenants, connectors; a `_FILE` variable here fails the render, because a secret goes through `credentials` |

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
migrate (DEC-0060). Until it is done the roles refuse to start against an empty schema and are
restarted.

**Every pod runs under the restricted profile**, the database included: not as root, no
privilege escalation, every capability dropped, the runtime's default seccomp profile and a
read-only root filesystem. The control plane's namespace can therefore enforce `restricted` too.

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
- **Egress:** to the per-job egress proxy (section 6), and to nothing else. Not to the
  cluster's DNS — with a proxy the job does not resolve names itself — not to the API server,
  not to the node, not to the link-local metadata address, not to the control plane's database.

The adapter labels what it creates so that the policies can select it: every object carries
`taktus/job: <the job's tag>` and `taktus/role`, which is `unit` for the unit's pod and `egress`
for the proxy's. So the exceptions are: ingress to `taktus/role: unit` on the contract port
from the control plane's namespace; egress from `taktus/role: unit` to `taktus/role: egress` on
port 3128; ingress to `taktus/role: egress` on port 3128 from `taktus/role: unit`; and egress
from `taktus/role: egress` to the cluster's DNS and to addresses outside the cluster, because
the proxy resolves the names the frame lists and connects to them. A policy cannot pair one
job's unit with its own proxy; the proxy's token does that (section 6).

In the control plane's namespace, the same default-deny, with egress to its database, to the
execution namespace's API-server-mediated job creation, to the hosts its connectors and models
need, and to the OTLP collector when one is configured.

Both policies are in the chart, and both are rendered whether or not the cluster enforces
them — see the next section for what happens when it does not.

The chart renders these exceptions by those labels. The proxy may leave the cluster to the
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

**What the policy cannot do: pair a unit with its own proxy.** The exceptions of section 5
select by role, so every unit may reach every proxy, and a unit could use another job's host
list. The proxy therefore asks for a token: a random value created for the job, held in the
job's Secret, and handed to both. The unit finds it in its proxy address
(`http://taktus:<token>@<address>:3128`), which every common client turns into a
`Proxy-Authorization` header by itself; the proxy answers 407 to a request without it. The
token is in no recorded configuration and lives as long as the job.

**If a cluster cannot enforce a NetworkPolicy at all**, the mechanism has no second half and
the host list means nothing more than a line in a bundle. Then the adapter **refuses to start a
job whose frame names allowed hosts**, and says so with the reason — it does not start the job
with an unenforced list. `execution.egress.enforce: false` is the operator's explicit,
recorded choice to run without it, and the run's ledger records that the frame was not
enforced. **The one thing that must never happen is the list quietly meaning nothing.**

On the target cluster the enforcement is present; it was verified read-only on 2026-09-23. The
verification and every detail of that cluster are in the operator's private note and not here,
because this repository is public (`CREDENTIALS.md`).

## 7. The cluster execution adapter

`src/taktus/adapters/driven/execution/kubernetes/`, a third implementation of the execution
port beside `process` and `container`, with `Isolation.CLUSTER`, selected by
`TAKTUS_EXECUTION=cluster` with `TAKTUS_EXECUTION_NAMESPACE`. It speaks to the cluster's API
with `httpx` alone, through the calls of the Role of section 1 and no other. It:

1. creates one `Job` per execution unit, in the execution namespace, from the frame: the image;
   requests equal to limits for CPU and memory; `activeDeadlineSeconds` of the wall clock plus
   the start timeout, as the cluster's backstop; `backoffLimit: 0`; `ttlSecondsAfterFinished`;
   a pod that satisfies `restricted` (section 4) and mounts no service-account token; the
   environment the contract names (`TAKTUS_UNIT_PORT`, `TAKTUS_UNIT_STATE_DIR`); and the
   credentials from a Secret it creates for the job — a `file` credential mounted from a key at
   its exact path, an `env` credential as a variable from a key, because the worker contract
   asks for it there, as the container adapter does. The pod's recorded configuration names the
   Secret's keys and never a value;
2. when the frame names hosts, creates the egress proxy as a second Job and a Service, with the
   frame's host list and the job's token (section 6), and waits for it to be ready within
   `startTimeoutSeconds`. Without hosts there is no proxy, and the job reaches nothing;
3. reaches the unit at its Service's address and speaks the worker contract to it, exactly as
   the other two adapters do — the port's interface does not change. The unit must answer
   health within `startTimeoutSeconds`; when it does not, the error says what the cluster says
   about the pod (an image that cannot be pulled, a pod that cannot be scheduled);
4. ends a job that exceeds the wall clock by deleting it, keeps the unit's log lines under the
   control plane's state directory, and deletes the job, its Secret, its Services and the proxy
   when the assignment ends, whatever the outcome. Every one of them is owned by the unit's Job,
   so that the cluster removes them too when the control plane died before it could: the
   deadline ends the Job, its time to live deletes it, and what it owns goes with it;
5. refuses, with the port's `ExecutionRefused` and before creating anything, a job it cannot
   give limits to, a frame that names hosts while `execution.egress.enforce` is false, and an
   isolation that does not suffice for the run's autonomy level. With network policies not
   enforced, a pod's network is open: the cluster then isolates the process and the filesystem,
   not the reach, and every job at level 3 or above — or at a level not known — is refused,
   as ADR-0002 refuses an unisolated unit.

The unit's state lives on the volume claim `execution.stateClaim` names, which the chart
renders; without one it is an empty directory that dies with the job, and the adapter's
startup log says so.

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
- **Backups.** A database deployed by this chart has no backup in it. That is its own pull
  request, and its destination off the node is NEED-0009; ADR-0013 C — a manual restore path,
  documented and exercised — is not satisfied by a volume snapshot nobody has restored. Until
  NEED-0009 is provided and the restore has been exercised, the instance holds no real work.

## 10. What is built, and what still waits

**Built** (#64): the chart, rendering sections 1, 2, 4 and 5 — both namespaces' objects, one
deployment per role, the database with its volume, the migrations, the two service accounts with
the Role, the default-deny policies both ways with their exceptions, the ingress; every secret a
mounted file. `helm lint` and `helm template` run in CI against `values.example.yaml`, and
`tests/governance/test_chart.py` reads the rendered manifests back. The image workflow of
section 3.

**Waits:**

- **the cluster execution adapter on a real cluster** (section 7). It is built (#65) and the
  chart wires it: `execution.kind: cluster` sets `TAKTUS_EXECUTION=cluster` with the namespace,
  the jobs' account, `execution.egress.enforce` and `execution.stateClaim`. The default stays
  `endpoint` until the install has run it on the target. The Role is the one of section 1
  (DEC-0061).
- **the install** on the target, with its ingress and webhook intake (#66), and the registry the
  images go to (NEED-0014).
- **backups** (section 9, #67).
