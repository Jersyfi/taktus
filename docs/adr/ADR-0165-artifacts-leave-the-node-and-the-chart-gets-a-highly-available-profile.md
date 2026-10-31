# ADR-0165 — Artifacts leave the node, and the chart gets a highly available profile

**Status:** accepted · extends ADR-0002 (the object store's alternative adapter) and ADR-0013 A (several instances) · issue #342

## Context

ADR-0013 A asks for several instances, load spread across them, and a restart without data
loss. The DevOps review of 2026-10-12 (K1) found the chart pinned to one node:

- every role mounts the one `ReadWriteOnce` volume `<release>-state`, which holds the artifact
  bytes;
- the database is one replica on a node-local volume;
- there is no disruption budget and no anti-affinity.

A `ReadWriteOnce` volume can be mounted on one node only. Two replicas of a role on two nodes
therefore cannot both reach the artifacts. The object store port (`ports/objectstore.py`)
already separates the content from the code that uses it. ADR-0002 names an S3-compatible store
as its optional alternative to the filesystem. Nothing implemented it.

Two terms are used below. An **S3-compatible store** is any object store that speaks the HTTP
interface first published for Amazon's S3, which many stores implement. A **disruption budget**
(`PodDisruptionBudget`) is the Kubernetes object that tells a voluntary disruption, such as the
draining of a node, how many pods of a set must stay up.

## Decision

### 1. Two adapters behind the one port, chosen by configuration

`TAKTUS_OBJECT_STORE` chooses the object store's adapter:

- `filesystem`, the default: each object is a file `<TAKTUS_STATE_DIR>/objects/<hex>`, as
  before.
- `s3`: each object is the key `<prefix>/<hex>` in one bucket of an S3-compatible store.
  `TAKTUS_OBJECT_STORE_ENDPOINT` and `TAKTUS_OBJECT_STORE_BUCKET` are required.
  `TAKTUS_OBJECT_STORE_PREFIX` and `TAKTUS_OBJECT_STORE_REGION` are optional; the region is
  `us-east-1` by default, which compatible stores accept. Requests use path-style addresses
  (`<endpoint>/<bucket>/<key>`).

The S3-compatible adapter signs every request with the interface's signature version 4. It is
written on the HTTP client the control plane already depends on. **No library is added**: the
only mandatory dependency stays PostgreSQL (ADR-0002). Its credential is two secret files,
`TAKTUS_OBJECT_STORE_ACCESS_KEY_ID_FILE` and `TAKTUS_OBJECT_STORE_SECRET_KEY_FILE`
(`CREDENTIALS.md`). Neither is ever logged.

Both adapters keep the same bounded cache in memory (`TAKTUS_OBJECT_CACHE_MB`, #311).

### 2. What every adapter holds to

One suite, `tests/adapters/objectstore/`, runs against every adapter:

- `put` returns `sha256:` over exactly the bytes, and `get` of that digest returns them.
- Writing the same bytes twice is one object.
- A digest never written reads as absent (`None`).
- **Bytes whose digest is not their name read as absent.** A store that returns other bytes
  than were written must not let them reach a step as content. The adapter logs the mismatch.
- **A store that cannot be reached raises `ObjectStoreUnavailable`.** It never answers
  `None`, because "the content is gone" and "the store is down" lead to different actions.
- An object outlives the process that wrote it: a new adapter over the same place reads it.

### 3. The highly available profile

`profile: ha` is the chart's third profile, beside `small` and `standard`:

- one deployment per role, as `standard`, with **at least two replicas of each role**. The
  scheduler and the automation role are elected; their second replica waits and takes over.
  The render fails below two.
- **no volume shared by roles.** The profile requires `objectStore.kind: s3`; the state
  directory is a volume of the pod's own (`emptyDir`). The render fails with the filesystem
  store.
- **one disruption budget per role**, `minAvailable: 1`.
- **anti-affinity per role** by node: two replicas of a role prefer two nodes
  (`ha.antiAffinity: preferred`, the default). `required` refuses to place them on one node.
  `required` needs one node more than the replicas of a role, or a rolling update cannot place
  its new pod.
- **no database of the chart's own.** The profile requires `database.deploy: false`. The chart's
  own database is one replica, and the profile refuses it. The external server is the
  operator's. It must run with a standby replica, archive its write-ahead log for
  point-in-time recovery, and keep one address across a failover. A PostgreSQL operator in the
  cluster provides that, and so does a managed server.

### 4. The backup and the S3-compatible store

With `objectStore.kind: s3` there is no state volume to archive. `backup.objects` must then be
false, and the render fails otherwise. The store keeps the objects off every node already. Its
durability is the store's: versioning, replication and retention are its operator's
configuration.

### 5. Moving an instance from the filesystem to the S3-compatible store

The names do not change: the file `<hex>` becomes the key `<prefix>/<hex>`. A person copies the
directory `objects/` into the bucket with any client of the interface, sets the configuration
and restarts. Taktus is not needed for it (UC-4.12). `deploy/k8s/README.md` §2 gives the steps.

## Alternatives

- **A `ReadWriteMany` volume** (a network file system) shared by every role. It keeps the
  filesystem adapter, but puts a second storage system under the instance. Its behaviour
  under concurrent writes differs from one provider to the next. The object store's
  content addressing needs nothing of the kind: an object is written once under its digest.
- **A client library for the interface.** It would be a second large dependency for two
  requests: put and get of one key, signed. The signing is a published algorithm, checked
  here against an independent server's implementation.
- **The chart deploys a PostgreSQL operator's cluster object.** It would make one operator, and
  its custom resources, a requirement of the chart. Which server the database runs on is the
  operator's choice; the profile states what that server must provide.
- **A required anti-affinity by default.** On a cluster of two nodes it blocks every rolling
  update of a role with two replicas.

## Consequences

- An instance can run its roles on several nodes, and lose one, without losing an artifact.
- The deployment identity needs the right to manage `PodDisruptionBudget` objects
  (`policy`) in the control plane's namespace for the profile `ha`. The profiles `small` and
  `standard` render none, and need none.
- The roles reach the store through `networkPolicy.controlPlaneEgress`, as they reach an
  external database.
- A failed read of the store now fails the step that needed it, instead of reading as missing
  content. A mismatched object reads as missing, in both adapters.

## Where this promise ends

- **The database's availability is the operator's.** The chart refuses its own single
  database in the profile `ha`, and it cannot see whether the external server has a replica or
  archives its log. The promise is that the profile renders no single point of failure the
  chart owns; not that the server behind `database.url` has none.
- **The store's durability is the store's.** Taktus writes each object once and never deletes
  one. Whether the store keeps versions, replicates or loses data is the store operator's
  configuration. The backup does not archive the bucket.
- **Not every component is replicated.** The connectors run one pod each. The egress gateway
  runs two replicas and has no disruption budget. A drained node can therefore stop a channel
  for the time its connector needs to start elsewhere.
- **Shown by rendering, not on a cluster of several nodes.** `tests/governance/test_chart.py`
  checks what `helm template` renders for the profile. The suite runs the S3-compatible
  adapter against a local server of the interface. Neither a failover of a node nor load on
  several nodes has been exercised; the nightly cluster test installs the profile `small`.
- **The interface is a subset.** The adapter uses put and get of one key, path-style, with
  signature version 4. A store that accepts only virtual-hosted addresses, or another
  signature, is not served.
- **The external security review of `1.0.0`** is to cover the profile. It has not taken place.
