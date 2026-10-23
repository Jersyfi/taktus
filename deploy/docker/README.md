# Docker

| File | Purpose |
|---|---|
| `compose.yml` | **the deployment shape**: Taktus and PostgreSQL, two containers for the control plane (ADR-0002). No worker: a worker is configured by endpoint, or started by the execution port (`TAKTUS_EXECUTION`) |
| `compose.reference-worker.yml` | **development only**, layered over `compose.yml`: the reference worker in its own image, reached by endpoint, for trying a bundle out and for `verify.sh` (`make up-dev`) |
| `Dockerfile` | the control plane image, every role, selected at start by `TAKTUS_ROLES`; carries no worker code (DEC-0011). The web app is built in a stage of its own with Node, and only its static build is carried over; the runtime holds no Node (ADR-0063). `npm ci` gives up a request that stalls after 30 s and retries it, so that a stalled download is retried rather than stopping the build (#360). It runs as user 999, pinned by number because the chart runs it as that number (`deploy/k8s/`). On a version tag, `.github/workflows/images.yml` builds it and each worker's image for the registry the repository names |
| `secrets.sh` | writes the two secret files `compose.yml` reads, once, under `secrets/` (ignored by git); the directory is closed to other host users and the files are readable, because the containers read them as their own user |
| `verify.sh` | the end-to-end check: from nothing, the image checked for worker code, a run, the container killed, restarted, the run resumed |
| `upgrade.sh` | the upgrade test (ADR-0124): the previous release from its tag's compose files and published images, a run in each of five states, upgraded to this checkout; every run continues at its boundary and no completed step runs again (`make verify-upgrade`, and the workflow `upgrade` on every release tag) |
| `taktus.env` | not in the repository: the operator's own settings, `TAKTUS_NAME=value` per line, read by `compose.yml` when it exists; never a secret value (ignored by git) |
| `.env` | not in the repository: what Docker Compose itself reads every time, the host port `TAKTUS_HTTP_PORT` above all, so that a port chosen once is kept by every later `make up` (ignored by git). `TAKTUS_HTTP_PORT` in `taktus.env` changes nothing: inside the container the port is always 8080 |
| `compose.dev.yml` | the development database: PostgreSQL alone, bound to `127.0.0.1`, trusting local connections, for `uv run taktusctl run` and the tests |

The reference worker's image is `workers/script/Dockerfile`; the coding worker's is
`workers/claudecode/Dockerfile`. Neither is part of the control plane image.

## Operating it

```bash
make up
```

That is the whole of it. `make up` writes a random database password and the database URL that
carries it under `secrets/` (never committed; existing files are kept, so a running database
keeps its password), builds the image, starts PostgreSQL, starts Taktus with every role in one
process, applies the migrations on start, and returns when readiness answers. The password
lives in two places that must agree: the secret files of the checkout and the database
volume. A fresh checkout next to an existing volume — a second clone, a worktree — writes new
secret files, and Taktus then cannot log in; keep the volume and copy the secret files over, or
run the second checkout under its own project name (`COMPOSE_PROJECT_NAME=taktus-2 make up`),
which gives it volumes of its own. Nothing here removes a volume. From then on:

| Where | What |
|---|---|
| `http://127.0.0.1:8080/health` | liveness: the process is alive |
| `http://127.0.0.1:8080/ready` | readiness: the database answers and is at the schema this build needs; `503` with the reason otherwise |
| `http://127.0.0.1:8080/runs`, `/runs/{id}`, `/runs/{id}/ledger` | the read API: a reader, with their account key in `Authorization: Bearer` or the web app's session cookie, reads the runs of their identity's tenant they may see and each run's ledger entries; `401` without a key |
| `http://localhost:8080/app/` | the web app: a reader signs in with their account key once per browser, stays signed in in every tab for `TAKTUS_SESSION_HOURS` (12 by default) or until *Sign out*, and starts at the overview of what they may see, and goes down to each process and run, live (ADR-0063, ADR-0119). Open it at `localhost`: a browser keeps the sign-in's `Secure` cookie for `localhost` and over HTTPS only |
| `http://127.0.0.1:8080/levels/runs/{id}` | the run level the web app draws, with an account key; `/levels/processes/{id}` the process level (ADR-0064); `/levels/overview` the overview (ADR-0067); `/levels/origins/{run}/{step}` the origin of a result (ADR-0068); `/vocabulary` is the visual vocabulary (ADR-0059) |
| `http://127.0.0.1:8080/intake/{channel}` | webhook intake for a channel a connector serves (`TAKTUS_CONNECTORS`); the sender is placed by the link of their account, and an unknown sender is answered in the channel and nothing is kept (ADR-0040) |
| `http://127.0.0.1:8080/intake-events/{id}/complete` | a caller, with their account key, completes an accepted delivery of their own tenant into a command that acts as the identity the sender's account is linked to; `401` without a key |
| `http://127.0.0.1:8080/identity/link-codes` | a person, with their account key, creates the code that links an account on a channel to their identity |
| `http://127.0.0.1:8080/decisions` | a decider, with their account key, lists the decision requests addressed to a role they hold, answers one, and confirms how the answer was read; `/decisions/response-times` shows them their own (ADR-0042) |
| `http://127.0.0.1:8080/owner/reports` | the owner, or someone the owner named, with their account key, reads what is needed from the owner, each report with its deliveries and history; `/owner/reports/{id}/text` is its repository text (ADR-0045) |
| `docker compose -f deploy/docker/compose.yml exec taktus taktusctl tenant create "Acme"` | create a tenant; prints the identifier Taktus generated for it. `tenant rename` changes its display name, `tenant list` lists every tenant. The running daemon serves a new tenant without a restart (ADR-0104) |
| `docker compose -f deploy/docker/compose.yml exec taktus taktusctl identity add idn_ada` | add an identity; prints its account key once. `identity links` and `identity revoke` see and revoke the links of a tenant; `--role` and `identity roles` set the roles it holds |
| `docker compose -f deploy/docker/compose.yml exec taktus taktusctl anchors set /path/anchors.json` | configure the tenant's anchors; `anchors show` prints those in force — the shipped default while none is configured (ADR-0042) |
| `docker compose -f deploy/docker/compose.yml exec taktus taktusctl owner-channel set /path/owner-channel.json` | configure where what is needed from the owner reaches them — the owner, whom they named, the channel and address, the language; `owner-channel show` prints it (ADR-0045) |
| `docker compose -f deploy/docker/compose.yml exec taktus taktusctl submit --process …` | queue a bundle for the daemon; prints the run's identifier |

`make down` stops the containers and keeps every volume — the database, the artifact bytes,
and the reference worker's state if it ran. Removing a volume is the operator's explicit act
(`docker volume rm taktus_taktus-postgres`), never a make target: nothing here deletes data
without asking (CLAUDE.md §9). The configuration is the `TAKTUS_*` variables of
`.env.example`; `compose.yml` sets what a container needs (`0.0.0.0`, the secret file,
migrations on start) and passes `TAKTUS_ROLES`, `TAKTUS_PATH_PREFIX`, `TAKTUS_WORKER`,
`TAKTUS_HTTP_PORT`, `TAKTUS_SHUTDOWN_CEILING_SECONDS` and `TAKTUS_LOG_LEVEL` through from
the environment of `make up`. Every other setting goes into `deploy/docker/taktus.env`, which
the operator writes and git ignores; a variable `compose.yml` names itself wins over it. The
administration guide's pages *Installing from nothing* and *Upgrading*
(`docs/guides/administration/`) take a stranger through all of it.

**Readiness and health are different questions.** A container whose database is gone answers
`503` on `/ready` and `200` on `/health`: it must not receive traffic, and it must not be
restarted in a loop either — restarting it would not bring the database back. The compose
health check probes `/ready`, so that `--wait` returns only once Taktus can work.

**Shutdown.** `docker compose stop` sends SIGTERM and waits `stop_grace_period`, which is the
shutdown ceiling. Taktus stops accepting work, lets every running step reach its boundary, writes
the checkpoint, releases its claim, and exits; a restart resumes at that boundary with at most
one step lost (ADR-0005, ADR-0013 A). A container that is killed instead — no signal, no chance
— leaves its run claimed for at most `TAKTUS_LEASE_SECONDS` (default 60), after which the next
runner recovers it at its last persisted boundary.

**A worker.** Two containers are the control plane: Taktus and its database. They run every
process built from `rule`, `statistics`, `wait` and `human` steps on their own. A process with
a `worker` step needs one execution unit in addition, and an execution unit is by design not
Taktus: workers are separate deployables behind the worker contract, each with its own image,
and **the control plane image contains no worker code** (DEC-0011). A worker executes foreign
code — that is its purpose and the reason execution is isolated at all — and code that is not
in the image cannot be started from a compromised control plane. `verify.sh` checks the built
image for it, and `tests/architecture` checks the Dockerfile.

`compose.yml` therefore starts no worker. How the control plane reaches one is the execution
port's configuration (`docs/architecture/contracts.md` §2.4): `TAKTUS_WORKER` names a worker
that is already running, reachable by endpoint — the default, and what
`compose.reference-worker.yml` sets; `TAKTUS_EXECUTION=container` makes the control plane
start one container per job from a worker image, with limits and a network allowlist, which
needs the container engine's socket mounted into the Taktus container. For development, `make
up-dev` layers the reference worker in its own image over the deployment:

```bash
make up-dev
```

## Models, and a gateway in front of them

A step on a model names a purpose, and Taktus routes it through that purpose's chain of models
(ADR-0116). `TAKTUS_MODELS` names the models in order, and each is configured under
`TAKTUS_MODELS_<NAME>_…` (`.env.example`). Each declares where it processes, `own`, `eu` or
`elsewhere`. `taktusctl residency set --location eu` keeps a tenant's steps on models the rule
permits. A model that answers `429` or fails is passed over for a while, and the step moves to
the next model at its boundary. The provenance of every answer names the model that gave it.

**A gateway is supported as a pass-through, and only so.** A gateway is a proxy that answers
for several providers in one dialect. Taktus does its own routing, because a gateway's fallback
hides from the ledger which model answered, where it processed, what it cost and how long the
step waited (ADR-0116 §8). A gateway may stand behind a model of the chain in this profile:

| Setting of the gateway | Pass-through profile |
|---|---|
| aliases | one alias for one model of one provider; each alias is one entry of `TAKTUS_MODELS` |
| fallbacks, retries on another model, load balancing, automatic model choice | off |
| response cache, semantic cache | off |
| prompt rewriting, compression, injected system prompts | off; conformance check M-02 fails an endpoint that adds text |
| its own budgets | off, or set above Taktus's budget as an outer backstop only |
| location | declared as the widest location of the provider behind the alias |

Run `taktusctl conformance run --contract model/v1` against each alias. A gateway set up
otherwise is not supported: Taktus cannot show which model answered or keep a residency rule.

**OmniRoute is not supported.** By default it chooses the model itself, falls back to other
providers on its own, and compresses prompts. Each of these breaks the provenance or the
residency rule above. It also reaches models through consumer subscriptions in ways a
provider's terms may forbid (`docs/research/2026-10-12-market-review.md`, part 3).

## Verifying the promise

```bash
make verify-compose
```

`verify.sh` does, from nothing: `make up-dev`, the deployment with the reference worker in
its own image; checks that the control plane image holds no worker code; adds the identity
`idn_verify`, which reads the API and submits and confirms the run, since nothing executes
without an identity; queues a bundle
whose worker step runs 24 commands, confirming each step as an operator would, since the bundle
runs at autonomy level 2 (`taktusctl submit --resume RUN --approve STEP`, ADR-0039); waits until
that step has persisted a boundary; kills the
application container with SIGKILL; starts it again; waits for the run to finish; and checks
through the read API that the run was recovered at its last boundary (`run.recovered` in the
ledger; the worker step started once and adopted after the restart, ADR-0038), that every
artifact exists exactly once, and that the ledger's chain is intact. It exits 0 when every step held and leaves the containers running.

**Finding.** Two containers suffice for the control plane. The end-to-end check needs a third
process — an execution unit — because a process with a worker step needs a worker, and no
worker is part of Taktus. That is ADR-0002's shape, not a departure from it.

## Development database

`make db-up` starts PostgreSQL alone (`compose.dev.yml`, no password, `127.0.0.1` only) and
waits until it accepts connections; `make migrate` brings it to the current schema
(`TAKTUS_DATABASE_URL=postgresql://taktus@127.0.0.1:5432/taktus`); `make db-down` stops it and
keeps the volume. When port 5432 is taken on the machine, `TAKTUS_DB_PORT` picks another host
port, and the URL carries that port. Removing the volume is the operator's explicit act
(`docker volume rm taktus-dev_taktus-dev-postgres`), never a make target.
