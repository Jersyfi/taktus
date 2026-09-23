# Credentials

**This register describes every credential as a parameter — what it is for, which permissions it
needs, how often it rotates, and the configuration key through which an operator supplies it. It
never holds a value, and it never holds a deployment's name for one.**

The repository is public. No secret value, token, key or private certificate ever enters this
history, a file, a log or a message. A finding is handled as: rotate first, clean up second.

Two rules meet here and both hold. *Names, never values* has been the rule since the first
commit. *Deployment-specific names belong in the operator's private configuration, not in a
public repository* is the second: the name a secret has in one environment — a path in a secret
store, a key in a vault, a variable in a deployment — is that environment's business and does
not survive a move to another. What survives the move is the **parameter**: the thing the
software needs, described by what it is for. The operator maps each parameter to a concrete
secret wherever they keep theirs, and that mapping is theirs.

Configuration references a parameter by its **configuration key** (`database.url`) or, where a
contract carries the reference, by the **name the call names** (a credential reference in an
assignment or a connector call). The operator supplies the value under that key or name; the
software reads it at the moment of use and keeps nothing.

**One pattern, for every credential and every reader.** A secret value is read from a file, and
the variable that holds that file's path is `TAKTUS_<KEY>_FILE`, the configuration key in
capitals (CLAUDE.md §9). For a credential the key is `credential.<name>`, so the variable is
`TAKTUS_CREDENTIAL_<NAME>_FILE` — the same variable whoever reads it: the composition root, the
execution adapter that starts a unit, a worker started by endpoint, `tools/first_run.sh`. One
credential has one variable. A second name for the same credential was a defect, corrected in
DEC-0018.

## The parameters

| Parameter | What it is for | Permissions it needs | Rotation | How an operator supplies it | Needs request |
|---|---|---|---|---|---|
| **Database connection** | how an instance reaches its PostgreSQL database. The whole URL is handled as a secret because it may carry the database password | a login that may connect to the instance's database, run the migrations, and use the application role the migrations create (`taktus_app`); nothing beyond that database (ADR-0020: one database per instance) | on the database's own schedule; changing the password on the server and the URL in the instance's configuration is one move | configuration key `database.url` — a file whose path is in `TAKTUS_DATABASE_URL_FILE` (read by the composition root through the configuration port; a secret is read from a file, never from a variable, because variables leak into process listings and child processes). The inline `TAKTUS_DATABASE_URL` is accepted for a URL that carries no password: the development database (`deploy/docker/compose.dev.yml`) has none and trusts local connections only. `make migrate` reads the same key through `migrations/env.py`; `compose.yml` hands the database its own password through `POSTGRES_PASSWORD_FILE` | none — `make up` writes it (`deploy/docker/secrets.sh`, `POSTGRES_PASSWORD_FILE`); on the platform it is part of the interface the platform note describes, NEED-0004 |
| **Repository access token of the requesting identity** | what the reference repository connector acts with when it reads an issue, opens a pull request, comments, or triggers a pipeline. It is **the requesting identity's** token with that identity's scopes; the connector has none of its own (`contracts/connector/v1` §5) | the requesting identity's permissions in the repository, and no more: read issues and pull requests, write pull requests and comments, trigger pipelines — whichever the process actually uses. The source system's permissions remain in force through it | whenever the hosting service's policy says, at the expiry the token was issued with, and at once when the identity leaves or the token may have been seen; revoke at the hosting service and issue a new one for the same identity, into the same file. A renewal is raised as its own needs request one week before the expiry | referenced **by name** in every call's context; the connector's runtime — whoever starts the connector — makes the value available under that name, in its environment or as a file it can read, before the call (`src/taktus/adapters/driven/connectors/github/README.md`). The connector reads it at the moment of the call and keeps nothing; the file's path is in `TAKTUS_CREDENTIAL_REPOSITORY_TOKEN_FILE`, which is what `tools/first_run.sh` reads | NEED-0002, provided 2026-09-22; NEED-0006 renews it before it expires |
| **Webhook signing secret** | the secret the hosting service signs webhook deliveries with; the connector refuses every delivery it cannot verify against it, before the body is read (`contracts/connector/v1` §7) | none — it is a shared secret, not an account. It must be the same on both sides | when the hosting service's policy says, or when it may have been seen; set the new secret on the webhook at the hosting service and in the connector's environment in one move, after which deliveries signed with the old one are refused | the name the connector's declaration lists under `credentials` with purpose `intake`; the connector reads the value from its environment under that name at the moment of each delivery | NEED-0004 — set at the hosting service and on the deployed instance in one move once the platform's interface says where; not needed for `taktusctl run` |
| **A credential an assignment references** | what a `worker` step's execution unit is given at runtime, under the name the assignment carries — `VCS_TOKEN` for a repository token, a signing key. The process defines the name; the unit reads the value under it (`contracts/worker/v1` §3) | whatever the unit's task needs and no more; the process names the credential, so the permission is the process's declaration | the source system's schedule; the unit stores nothing, so a rotation is a change of the file the operator maps | configuration key `credential.<name>` — a file whose path is in `TAKTUS_CREDENTIAL_<NAME>_FILE`, read by the execution adapter at the moment a unit is started and injected into the unit: as its environment (`process`, `container`) or as a file in memory (`container`). For a worker configured by endpoint, whoever starts the worker puts the value into its environment under the name | the need of the credential the process names; NEED-0001 for `coding_credential` of the dev-orchestration blueprint |
| **Coding agent API key** | what the coding worker's agent authenticates with in `api-key` mode, referenced as `CODING_AGENT_API_KEY` (or the name `--credential` gives) | the agent's own account: usage billed to it, nothing else | the provider's policy, and the validity the key was issued with where it has one — a key is not necessarily perpetual; at once when it may have been seen. A rotation replaces the content of the file in use and deletes the old key | as the row above: `TAKTUS_CREDENTIAL_CODING_AGENT_API_KEY_FILE`, the same variable whether the unit is launched by the execution adapter or started as an endpoint worker by `tools/first_run.sh`. The worker hands it to the agent under the agent's own variable and never logs it (`workers/claudecode/README.md`) | NEED-0001, provided 2026-09-22; NEED-0005 renews it before it expires |
| **Coding agent subscription token** | the same, in `session` mode: the long-lived token the agent's `setup-token` command issues for a subscription, referenced as `CODING_AGENT_SESSION` | the subscription's window; nothing else | when it expires or may have been seen; a session that expires mid-run halts the assignment at its last boundary, and a new token resumes it | as the row above, `TAKTUS_CREDENTIAL_CODING_AGENT_SESSION_FILE`, whichever way the unit is started | NEED-0001 — not the way it was provided; the owner chose the API key. A subscription token needs its own renewal when it is ever used |
| **Model API key** | the bearer credential the model endpoint `llm` steps ask (`TAKTUS_MODEL_ENDPOINT`) requires, if it requires one; a local model server needs none | the endpoint's own account: usage billed to it, nothing else | the provider's policy; at once when it may have been seen | configuration key `credential.model_api_key` — a file whose path is in `TAKTUS_CREDENTIAL_MODEL_API_KEY_FILE`, read through the configuration port when the model adapter is built and revealed only into the request header; masked in the startup log (`src/taktus/adapters/driven/models/`) | NEED-0003, provided 2026-09-22 as the file of NEED-0001; one file, one renewal, NEED-0005 |
| **Deployment kubeconfig** | how whoever installs Taktus on a cluster reaches that cluster's interface: the address, the cluster's certificate authority and a token. It is **not** the identity Taktus runs as — that one is created by the chart and may create jobs in one namespace and read their logs (ADR-0025: an instance never administers the infrastructure it runs on) | in the namespaces the instance is given and nowhere else: the resources a chart installs, and pods and their logs read-only. A namespaced role, never a cluster role; no nodes, no other namespace | when the token expires, and at once when it may have been seen; a new token into the same file, and the old one revoked at the cluster | configuration key `credential.deploy_kubeconfig` — a file whose path is in `TAKTUS_CREDENTIAL_DEPLOY_KUBECONFIG_FILE`, used by whoever runs the install and by nothing inside Taktus | NEED-0007 |
| **Telemetry endpoint headers** | what the OTLP endpoint that collects the spans needs — an authorisation token, typically — as `name=value` pairs separated by commas | write to that endpoint's traces; nothing else | the platform's policy | configuration key `otlp.headers` — a file whose path is in `TAKTUS_OTLP_HEADERS_FILE`; masked in the startup log | none — optional; no process depends on telemetry being exported, and no collector has been chosen. A need is raised when one is |
| **CI read token** | lets the secret scan in the repository's own CI read the commits of a pull request | read access to the repository's pull requests; nothing else | none needed: the CI service creates it per workflow run and revokes it when the run ends; it is never stored | the workflow (`.github/workflows/ci.yml`, step `secrets`) receives it from the CI service; no operator supplies it | none — the CI service creates it per run; nobody supplies it |

The conformance gate and the connector tests hand random values to the reference connector and
to the fake of its service (`FAKE_REPOSITORY_TOKENS`) for the length of one test; they are
generated in the test, never committed, and the tests fail if one appears in an answer or a log.
The coding worker's gate does the same under `CODING_AGENT_API_KEY` and `CODING_AGENT_SESSION`
with a stand-in for the agent, and the container adapter's tests hand random values through
`TAKTUS_CREDENTIAL_*_FILE` files and check from inside the job that they are on no filesystem,
in no recorded configuration and in no log.

## When a credential expires anyway

A renewal can be missed. What Taktus does then is the same for every parameter in this
register, and it is stated here so that nobody has to guess from the code:

- **It halts at a step boundary, with the cause.** The step that used the credential ends
  `failed`, with the refusal the service gave as its reason, and the run escalates at that
  boundary. Every step before it stays completed with its provenance; nothing is half done.
- **It never aborts.** The run is not discarded. A new value in the same file and a resume
  continue at the step that failed; the escalation's last line says how.
- **It never retries silently.** A connector call refused as `unauthenticated` is recorded
  with effect `none` and retryable `false` — the connector contract requires it and the
  conformance suite checks it (C-03). A model call refused by its endpoint fails the step and
  stops the run. Nothing outward is repeated in the hope that it works the second time.

The cost of a missed renewal is therefore a halted run, not a wrong result and not a partial
write. That is why a renewal is raised as a needs request one week before the expiry
(ADR-0028's timing rule), and not why it may be late.

## The last column

Every row names the **needs request** under which the owner provides the parameter —
`NEED-NNNN`, a record under `docs/decisions/` with the steps (ADR-0028) — or says `none` with
the reason nobody has to provide it. `make gate-decisions` fails a row that does neither, a
row naming a need that has no file, and a `<NAME>_FILE` variable in the code that this register
does not describe. That is how a pull request that builds something whose real use depends on
a credential is made to raise the need in time: the variable forces the row, the row forces the
need.

## Rule for every session in this repository

Never ask for a secret value. Write configuration that references a parameter — by configuration
key or by the name a call names — describe the parameter here, and raise the needs request
that tells the owner which secret to create and how, when the need becomes foreseeable. Never write a deployment's name for a secret into this repository: the
operator's mapping from parameter to secret is theirs.
