## Worker steps on one server, without a cluster

This section is for an operator who runs Taktus on one server with Docker Compose and no
Kubernetes. It says how the steps of a **worker** run there. A worker is a separate program
that carries out a step Taktus does not do itself: the coding worker changes code under the
capability `code.edit`, and the browser worker checks web pages under `browser.check`.

The compose file starts Taktus, its database and the backup. It starts no worker. A process
built only from `rule`, `statistics`, `wait` and `human` steps needs none. A process with a
`worker` step needs an **execution unit**: one running worker, from the worker's own image.
The image of Taktus carries no worker code (DEC-0011).

### Two ways on one server

The setting `TAKTUS_EXECUTION` says how Taktus reaches a worker. Two of its values suit one
server.

| | `endpoint` (the default) | `container` |
|---|---|---|
| Who starts the worker | you, as a service of its own | Taktus, one container per job |
| Resource limits of a job | not enforced by Taktus | CPU, memory without swap, process count, wall clock |
| The hosts a step may reach (`frame.allowed_hosts`) | not enforced by Taktus | enforced by the egress gateway |
| Where a credential comes from | the worker's environment, put there by whoever starts it | a file Taktus reads at each start, handed to the job in memory |
| What Taktus needs from the server | nothing beyond the network | the container engine's socket |

Two more values exist and do not suit this shape. `process` starts a worker as a child process
of Taktus, without any isolation, and is refused from autonomy level 3 upwards. `cluster` needs
Kubernetes. The file `.env.example` describes all four.

From autonomy level 3, a step runs only on a worker whose maturity is *verified* (ADR-0039).
`workers/README.md` says that no worker shipped with Taktus is *verified* yet.

### The worker images

Each worker has its own image, built from its directory under `workers/`. Where a release's
images are published, the coding worker's is `<your-registry>/taktus-worker-coding:<version>`
and the browser worker's is `<your-registry>/taktus-worker-browser:<version>`
(`.github/workflows/images.yml`). `<version>` is the release's tag without its leading `v`.
To build them yourself from the release's checkout:

```bash
docker build -f workers/claudecode/Dockerfile -t <your-registry>/taktus-worker-coding:<version> .
docker build -f workers/browser/Dockerfile -t <your-registry>/taktus-worker-browser:<version> .
```

An image reference may end in `@sha256:<digest>`; the container adapter then pulls that digest
(`docs/architecture/contracts.md` §2.4). The adapter pulls a missing image without a registry
login. An image from a registry that asks for one must be pulled onto the server first, with
`docker pull`.

### By endpoint

You start each worker as a service of its own, and `TAKTUS_WORKER` names its base URL.
`deploy/docker/compose.reference-worker.yml` shows this shape for the reference worker; it is
for development and names no other worker. The repository ships no compose file that starts
the coding worker or the browser worker.

Both workers' images serve the worker contract on port 9000. The coding worker needs its
authentication mode in its environment, `CODING_AGENT_AUTH=api-key` or `=session`
(`workers/claudecode/README.md`). It also needs the credential the step references, such as
`CODING_AGENT_API_KEY`, in its environment under that name (`CREDENTIALS.md`, *A credential an
assignment references*).

Several workers on one instance are named in `TAKTUS_WORKERS`, in the order a step is matched
against them. Each worker of kind `endpoint` then needs its own base URL,
`TAKTUS_WORKER_<NAME>_ENDPOINT`.

What Taktus does not do here: it enforces neither the limits nor the allowed hosts on a worker
it did not start. The worker itself refuses a tool call to a host outside the step's frame, and
the run records it; that is a record, not a wall. A process at autonomy level 3 or above needs an
isolated worker, and with this way providing one is yours (DEC-0022).

### In a container per job

With `TAKTUS_EXECUTION=container`, Taktus starts one container per job from the worker's image.
It speaks to the container engine through the engine's socket, over the engine's HTTP API.
Docker answers on that socket, and so does Podman. The adapter is
`src/taktus/adapters/driven/execution/container/`.

**What the socket gives Taktus.** Whoever can use the engine's socket can start any container,
with any image, any mount of the server's files and any privilege. The Taktus container
therefore holds the same power over the server as its administrator. Taktus uses it to start
each job without capabilities, without privilege escalation and without the socket. A
compromised Taktus could use it for anything. DEC-0011 keeps worker code out of Taktus's image;
with the socket, Taktus can still start any image the engine can pull. Accept this before you
mount the socket.

**The settings**, each a line of `deploy/docker/taktus.env`:

| Setting | What it is | Default |
|---|---|---|
| `TAKTUS_EXECUTION` | `container` | `endpoint` |
| `TAKTUS_EXECUTION_UNIT` | the worker's image, by reference; required | none |
| `TAKTUS_EXECUTION_ENGINE_SOCKET` | the socket's path inside the Taktus container | `/var/run/docker.sock` |
| `TAKTUS_EXECUTION_NETWORK` | the network the Taktus container is on, which the egress gateway joins | none |
| `TAKTUS_EXECUTION_EGRESS_IMAGE` | the egress gateway's image: any image with `python3` on its path | `python:3.13-slim` |
| `TAKTUS_EXECUTION_GATEWAY_KEY_FILE` | the file with the egress gateway's key (`CREDENTIALS.md`, *Egress gateway key*) | none: a key is drawn at each start |
| `TAKTUS_EXECUTION_CPUS`, `_MEMORY_MB`, `_WALL_SECONDS` | a job's limits: CPU cores, memory, seconds | 1.0, 1024, 3600 |
| `TAKTUS_EXECUTION_START_TIMEOUT_SECONDS` | how long a job's worker may take to answer | 60 |
| `TAKTUS_EXECUTION_UNIT_PORT`, `_UNIT_STATE_DIR` | where the worker serves and keeps its checkpoints, inside its container | 9000, `/var/lib/taktus/unit` |
| `TAKTUS_EXECUTION_SERVICE_HOSTS` | the hosts the worker's own service needs, such as the coding agent's provider | none |
| `TAKTUS_EXECUTION_UNIT_ENV` | variables the worker needs to start, never a secret: `CODING_AGENT_AUTH=api-key` | none |
| `TAKTUS_CREDENTIAL_<NAME>_FILE` | the file of a credential a step references, read at each job's start | none |

With several workers, `TAKTUS_WORKERS` names them, and each setting above is read first as
`TAKTUS_WORKER_<NAME>_…`, such as `TAKTUS_WORKER_CODING_EXECUTION_UNIT`. A named worker's
credential is `TAKTUS_WORKER_<NAME>_CREDENTIAL_<CREDENTIAL>_FILE`, and it receives no other
(`.env.example`). For the two workers of this page:

```
TAKTUS_EXECUTION=container
TAKTUS_EXECUTION_NETWORK=taktus_default
TAKTUS_WORKERS=coding,browser
TAKTUS_WORKER_CODING_EXECUTION_UNIT=<your-registry>/taktus-worker-coding:<version>
TAKTUS_WORKER_CODING_EXECUTION_UNIT_ENV=CODING_AGENT_AUTH=api-key
TAKTUS_WORKER_CODING_EXECUTION_SERVICE_HOSTS=<the agent provider's API host>
TAKTUS_WORKER_CODING_CREDENTIAL_CODING_AGENT_API_KEY_FILE=/run/secrets/coding_agent_api_key
TAKTUS_WORKER_BROWSER_EXECUTION_UNIT=<your-registry>/taktus-worker-browser:<version>
```

`taktus_default` is the network Docker Compose creates for `compose.yml`, whose project is
named `taktus`. Without `TAKTUS_EXECUTION_NETWORK` the gateway publishes its port on
`127.0.0.1` of the server, which a Taktus that itself runs in a container cannot reach.

**What the Taktus container needs in addition**, beyond what `compose.yml` gives it:

- the socket, mounted at the path `TAKTUS_EXECUTION_ENGINE_SOCKET` names;
- access to it for the user the image runs as, number 999 (`deploy/docker/README.md`); the
  socket usually belongs to root and one group of the server;
- every credential file a `_FILE` setting names, mounted where it names it.

`deploy/docker/compose.container-execution.yml` adds the first two and sets
`TAKTUS_EXECUTION=container`, the socket's path and the network. Set `TAKTUS_ENGINE_SOCKET_GID`
to the group that owns the socket (`stat -c %g /var/run/docker.sock`) in the shell or in
`deploy/docker/.env`, the image in `taktus.env`, and start with:

```bash
make up EXECUTION=container
```

Credential files stay yours to mount, in a file of your own laid over these two.
`tests/deploy/test_compose_container_execution.py` holds the file to the settings Taktus reads
and has Compose accept it over `compose.yml`. `make start` does not lay it over; run `make up
EXECUTION=container` after it.

**Not proven.** No test of the repository runs Taktus inside a container with the socket
mounted and a job through it: `tests/integration/test_launched_container.py` runs Taktus on the
machine itself and starts its jobs through the socket. No test runs the browser worker as a job
behind the egress gateway.

**What one job gets** (`docs/architecture/contracts.md` §2.4, ADR-0115):

- a container of its own from the worker's image, without capabilities or privilege
  escalation, with the limits above; an engine that cannot limit memory or swap is refused
  before anything starts;
- an internal network of its own, `taktus-job-<job>`, with no route out;
- its credentials written into memory after the start, never on a volume, in the container's
  recorded configuration, on a command line or in a log;
- one named volume per worker for its checkpoints, `taktus-unit-state-<worker>`, which outlives
  the job so that a resumed step finds them; no other mount, and never the socket.

**The egress gateway.** One container per instance, `taktus-gateway-<a digest of its key>`,
started with the first job from `TAKTUS_EXECUTION_EGRESS_IMAGE`. It is the only other member of
each job's network, and it joins that network for the job's life. It does two things:

- **inbound**, on port 8080 and only on `TAKTUS_EXECUTION_NETWORK`: it forwards Taktus's
  requests to the worker in a job;
- **outbound**, on port 3128: it is an HTTP proxy that admits exactly the hosts the job's token
  names, and refuses every other host and every address on a job's network. The token is
  signed with the gateway's key, minted for one job, and names the step's allowed hosts and,
  for an assignment, the worker's service hosts. A job whose step names no host gets no token
  and reaches nothing.

Without `TAKTUS_EXECUTION_GATEWAY_KEY_FILE`, Taktus draws a key at each start, and removes its
gateway when it stops. On a cluster, a network policy keeps the gateway off the cluster's own
address ranges (`execution.egress.exceptCidrs`). Here nothing does: a host a step names on the
server's own network is reached.

**Not covered.** The browser worker sets no proxy for the browser it drives, and no test runs it
under `container` or `cluster`. Whether a `browser.check` reaches its hosts through the gateway
is not shown by the repository.

### Checking a worker

`taktusctl conformance record worker.<name> --identity <identity> --tenant <tenant>` runs the
worker contract's conformance suite against a worker as the instance's configuration resolves
it, and records what it found. `taktusctl conformance list` prints every configured worker with
its maturity.

### Budget, backup and what stays on the server

Budgets and limits are the tenant's, the same on every shape: page *Budgets, limits, residency
and stops*. The backup of `compose.yml` holds the database and the stored files (page
*Restoring*). It does not hold the workers' volumes `taktus-unit-state-<worker>`. `make down`
keeps them, as it keeps every volume.
