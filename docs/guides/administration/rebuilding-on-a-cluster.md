## Rebuilding an instance on a cluster

This section is for an operator whose instance on a Kubernetes cluster is gone: its namespaces,
database, volumes, Secrets and Helm release. It installs the instance again, from nothing, with
everything a working instance has beyond a first install: its workers, its credentials, its name
for others, and its backup. A section named by its number is one of *Installing from nothing*
(`docs/guides/administration/first-install.md`). Every command of its section 3 holds; this
section says what comes before it, what goes into the values, and what follows it.

Placeholders: `<namespace>` is the control plane's namespace, `<execution-namespace>` the one
Taktus starts its jobs in; section 3 uses `taktus` and `taktus-execution`. `<release>` is the
Helm release's name, `taktus` in section 3. `<your-registry>` is your registry with its path.

### What comes back, and what does not

The chart's backup writes to an object store outside the cluster (`deploy/k8s/README.md` §11).
A backup there survived the deletion. With one, the rebuilt instance can take back its database
and its stored files: its tenants, identities, account keys, processes, runs and ledger. Without
one, the rebuilt instance starts empty.

No backup holds these, so they are made again:

- every Secret: the chart creates none except the egress gateway's key, and the values that fill
  them live in your own secret store;
- the volume claim of the workers' state in the execution namespace (`deploy/k8s/README.md` §9):
  a step that waited at a checkpoint there starts its work again;
- the images in your registry, where they were deleted too.

**Not described.** The restore of `deploy/k8s/README.md` §11 asks, in its step 4, for an empty
database. A first install migrates the database it creates right after creating it, so the
database is not empty afterwards. The repository does not say how to restore into a database the
install has already migrated.

### What the cluster and your workstation need

- **Kubernetes.** The repository states no minimum version, and the chart declares none.
- **Storage.** A default storage class, or one named per volume: `database.storageClass`,
  `state.storageClass`, `execution.stateStorageClass`. Choose `database.size` once: on a
  storage class that does not allow expansion, the database's volume cannot be enlarged later
  (`deploy/k8s/README.md` §2).
- **Network policies enforced.** Without them a job could ignore the egress gateway and connect
  out directly. On such a cluster, `execution.egress.enforce: false` is your stated choice, and
  it refuses every job whose step names a host, and every job from autonomy level 3
  (`deploy/k8s/README.md` §6).
- **An ingress controller**, only where people or webhooks reach the instance under a name of
  its own.
- **A registry** the cluster pulls from, holding the images below.
- **Two identities.** One may create namespaces; it is used once, for the namespaces. The
  other, the **deployment identity**, installs the chart. Its rights are exactly those of
  `deploy/k8s/README.md` §1, in the two namespaces and nowhere else. The repository describes
  those rights and ships no manifest that creates the identity. Its kubeconfig is the
  parameter *Deployment kubeconfig* of `CREDENTIALS.md`.
- **On your workstation:** `kubectl`, `git`, `make`, `docker`, and `helm` at the version the
  repository pins (`make helm` places it under `.tools/bin/`; `make start-cluster` takes `helm`
  from the path).

### The images

Section 3.2 builds and pushes the image of Taktus. An instance with more than that needs these
too, each tagged with the same `<version>`:

| Image | Built from | Needed for |
|---|---|---|
| `<your-registry>/taktus-backup` | `deploy/backup/Dockerfile` | the backup and the restore drill |
| `<your-registry>/taktus-worker-coding` | `workers/claudecode/Dockerfile` | steps of `code.edit` |
| `<your-registry>/taktus-worker-browser` | `workers/browser/Dockerfile` | steps of `browser.check` |
| `<your-registry>/taktus-connector-<name>` | the stage `<name>` of `connectors/Dockerfile` | each connector the instance runs |

```bash
docker build -f deploy/backup/Dockerfile -t <your-registry>/taktus-backup:<version> .
docker build -f workers/claudecode/Dockerfile -t <your-registry>/taktus-worker-coding:<version> .
docker build -f connectors/Dockerfile --target <name> -t <your-registry>/taktus-connector-<name>:<version> .
```

A connector's image is taken beside the image of Taktus, with the same tag, unless
`connectors.imagePrefix` names another place. `<name>` is one of the list
`taktus.shippedConnectors` in `deploy/k8s/chart/templates/_helpers.tpl`. Where the repository's
image workflow published a release, its artefact `digests.values.yaml` pins every image by
digest, and is given to Helm as a second values file (`deploy/k8s/README.md` §3).

### The namespaces

Create both as in section 3.3, as the identity that may create namespaces. Label both with
`restricted`, as the chart labels them where it creates them itself
(`deploy/k8s/chart/templates/namespaces.yaml`):

```bash
for ns in <namespace> <execution-namespace>; do
  kubectl create namespace "$ns"
  kubectl label namespace "$ns" \
      pod-security.kubernetes.io/enforce=restricted \
      pod-security.kubernetes.io/audit=restricted \
      pod-security.kubernetes.io/warn=restricted
done
```

The labels are set outside the chart because the deployment identity may not change a
namespace (DEC-0060). Where the identity that installs may create namespaces,
`namespaces.create: true` renders both, with these labels. The network policies select a
namespace by its name label, `kubernetes.io/metadata.name`, which the cluster sets itself.

### The Secrets

Create every Secret before the install, in `<namespace>` unless the table says otherwise. Each
holds one parameter of `CREDENTIALS.md`, which says what it is for, the permissions it needs
and how it rotates. The chart mounts each as a file and sets its `_FILE` variable; a value
never enters the values file.

| Parameter in `CREDENTIALS.md` | Named in the values by | Needed when |
|---|---|---|
| Database connection | `database.urlSecret`, `.urlKey`; the server's password `database.passwordSecret`, `.passwordKey` | always; section 3.3 creates both |
| Egress gateway key | nothing: the chart makes it, in both namespaces. Your own: `execution.gateway.keySecret`, `.keyKey`, a Secret of that name in both namespaces | a worker runs in the cluster |
| Coding agent API key | an entry of `credentials`, parameter `worker.<worker>.credential.coding_agent_api_key` | a coding worker runs |
| A credential an assignment references | an entry of `credentials`, parameter `credential.<name>`, or `worker.<worker>.credential.<name>` | a step references it |
| Model API key | an entry of `credentials`, parameter `credential.model_api_key` | the model endpoint asks for one |
| Repository app private key, Webhook signing secret | `connectors.repository.appKey`, `.webhook` | the repository connector runs |
| Chat token, Chat signing secret | `connectors.chat.secret`, `.tokenKey`, `.signingKey` | the chat connector runs |
| A further connector's credential | `connectors.others[].credentials`, `{name, secret, key}` | that connector runs |
| Backup store credential | `backup.store.secret`, `.accessKeyIdKey`, `.secretKey` | the backup runs |
| Backup private key | `backup.drill.identitySecret`, `.identityKey` | the drill restores an encrypted backup in the cluster |
| Object store credential | `objectStore.secret`, `.accessKeyIdKey`, `.secretKeyKey` | `objectStore.kind: s3` |
| Telemetry endpoint headers | `telemetry.otlp.headersSecret`, `.headersKey` | a collector asks for them |

Two Secrets the chart names are not parameters of `CREDENTIALS.md`: the registry's pull Secret,
`image.pullSecret`, and the certificate, `ingress.tls.secretName`. The chart mounts no
administration key, so tenants are administered with `taktusctl` alone on a cluster.

### The values

Start from the values of section 3.4, with a `profile` of section 3 or of
`deploy/k8s/README.md`, *Which profile*. Every key is described in
`deploy/k8s/chart/values.yaml`. What a full instance adds:

```yaml
execution:
  namespace: <execution-namespace>
  kind: cluster
  stateClaim: <a name for the workers' state claim>
  workers:
    - name: coding
      image: <your-registry>/taktus-worker-coding:<version>
      unitEnv: {CODING_AGENT_AUTH: api-key}
      serviceHosts: [<the agent provider's API host>]
    - name: browser
      image: <your-registry>/taktus-worker-browser:<version>
credentials:
  - parameter: worker.coding.credential.coding_agent_api_key
    secret: <the Secret>
    key: <its key>
networkPolicy:
  apiServer:
    cidrs: [<the API server's address range>]
  ingressController:
    namespace: <the ingress controller's namespace>
ingress:
  host: <the instance's public name>
  tls:
    secretName: <the certificate's Secret>
backup:
  enabled: true
  image:
    repository: <your-registry>/taktus-backup
    tag: "<version>"
  recipient: <an age public key>
  store:
    endpoint: <the store's address>
    bucket: <the bucket>
    secret: <the Secret>
    accessKeyIdKey: <its key>
    secretKey: <its key>
```

- `execution.kind: cluster` starts every worker step as a Job in the execution namespace
  (`deploy/k8s/README.md` §7). The chart then deploys the egress gateway there.
- `networkPolicy.apiServer.cidrs` is empty by default. The runner reaches the cluster's API to
  create its Jobs, and the default-deny policy lets it through only to these addresses.
- `networkPolicy.ingressController.namespace` is the one namespace allowed to reach the API of
  Taktus. Empty, nothing outside the namespace reaches it.
- The ingress serves a stream of changes that must not be buffered (`deploy/k8s/README.md` §2,
  `ingress.*`).
- `backup.recipient` encrypts each backup to a key pair you make off the instance. Keep the
  private key in your own store, never in the cluster unless you choose the drill there.
- The connectors and the model are the page *Configuring*; each connector is an entry of
  `connectors`.

The browser worker sets no proxy for the browser it drives, and no test runs it as a Job.
Whether a `browser.check` reaches its hosts through the egress gateway is not shown by the
repository.

### Install

As the deployment identity, without `--wait`:

```bash
.tools/bin/helm upgrade --install <release> deploy/k8s/chart --namespace <namespace> \
    -f <your values> [-f digests.values.yaml] --timeout 10m
kubectl -n <namespace> rollout status deployment --timeout=10m
```

The chart creates the database, and then runs the migrations as a job. Helm returns when that
job has finished. The roles refuse to start against an empty schema, so `--wait` would wait for
them before the job runs, and never finish (`deploy/k8s/README.md` §10). A failed migration is
read with `kubectl -n <namespace> logs job/<release>-migrate`.

`make start-cluster VALUES=<your values> ADDRESS=<the web app's address>` does the same
install and, after it, sections 4 and 5: the first tenant, its administrator `idn_admin` and the
account key, printed once. It then keeps the clock to a first rehearsal (section 6.1). Name the
owner as in section 5.1: without an owner-facing channel, nobody hears of a failed backup.

Continue with sections 6 and 7. A `taktusctl` command runs in a pod of the control plane; with
the profile `small` that is `kubectl -n <namespace> exec deploy/<release>-all -- taktusctl …`.

### Checks

| What | How |
|---|---|
| every role ready | `kubectl -n <namespace> rollout status deployment` |
| the instance, its release and the tenant's backup, alerts and incidents | `taktusctl health --tenant <tenant>`; exit code 2 when the database does not answer |
| readiness from outside | `kubectl -n <namespace> port-forward service/<release>-api 8080:8080`, then `curl -fsS http://localhost:8080/ready` |
| a process runs | section 7.1 |
| each worker starts as a Job, with its credential, through the gateway | `taktusctl conformance record worker.<name> --identity idn_admin --tenant <tenant>`; `taktusctl conformance list` shows each worker's maturity |
| the backup | `kubectl -n <namespace> create job --from=cronjob/<release>-backup <release>-backup-now`, then its log; `taktusctl backup list --tenant <tenant>` |

`make verify-kind` installs the chart into a kind cluster it fills itself, and is no check of an
existing cluster. The repository has no command that checks on a cluster that the gateway
refuses a host outside a step's frame.

### The backup, and practising the restore

Set it up before the instance holds anything worth keeping: `deploy/k8s/README.md` §11 says
what it writes and what its login needs. The restore drill, `backup.drill.enabled`, restores
the newest backup every week and verifies every tenant's ledger. With `backup.recipient` it
needs the private key; `deploy/k8s/README.md` §11 runs it off the instance instead.
Point-in-time recovery, `backup.pointInTime.enabled`, shortens what a loss can take to minutes.
How much each choice can lose, and for how long, is on the page *Restoring*.
