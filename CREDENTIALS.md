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

## The parameters

| Parameter | What it is for | Permissions it needs | Rotation | How an operator supplies it | Needs request |
|---|---|---|---|---|---|
| **Database connection** | how an instance reaches its PostgreSQL database. The whole URL is handled as a secret because it may carry the database password | a login that may connect to the instance's database, run the migrations, and use the application role the migrations create (`taktus_app`); nothing beyond that database (ADR-0020: one database per instance) | on the database's own schedule; changing the password on the server and the URL in the instance's configuration is one move | configuration key `database.url` — a file whose path is in `TAKTUS_DATABASE_URL_FILE` (read by the composition root through the configuration port; a secret is read from a file, never from a variable, because variables leak into process listings and child processes). The inline `TAKTUS_DATABASE_URL` is accepted for a URL that carries no password: the development database (`deploy/docker/compose.dev.yml`) has none and trusts local connections only. `make migrate` reads the same key through `migrations/env.py`; `compose.yml` hands the database its own password through `POSTGRES_PASSWORD_FILE` | none — `make up` writes it (`deploy/docker/secrets.sh`, `POSTGRES_PASSWORD_FILE`); on the platform it is part of the interface the platform note describes, NEED-0004 |
| **Repository access token of the requesting identity** | what the reference repository connector acts with when it reads an issue, opens a pull request, comments, or triggers a pipeline. It is **the requesting identity's** token with that identity's scopes; the connector has none of its own (`contracts/connector/v1` §5) | the requesting identity's permissions in the repository, and no more: read issues and pull requests, write pull requests and comments, trigger pipelines — whichever the process actually uses. The source system's permissions remain in force through it | whenever the hosting service's policy says, and at once when the identity leaves or the token may have been seen; revoke at the hosting service and issue a new one for the same identity | referenced **by name** in every call's context; the connector's runtime — whoever starts the connector — makes the value available under that name, in its environment or as a file it can read, before the call (`src/taktus/adapters/driven/connectors/github/README.md`). The connector reads it at the moment of the call and keeps nothing; `tools/first_run.sh` takes the file's path from `REPOSITORY_TOKEN_FILE` | NEED-0002 |
| **Webhook signing secret** | the secret the hosting service signs webhook deliveries with; the connector refuses every delivery it cannot verify against it, before the body is read (`contracts/connector/v1` §7) | none — it is a shared secret, not an account. It must be the same on both sides | when the hosting service's policy says, or when it may have been seen; set the new secret on the webhook at the hosting service and in the connector's environment in one move, after which deliveries signed with the old one are refused | the name the connector's declaration lists under `credentials` with purpose `intake`; the connector reads the value from its environment under that name at the moment of each delivery | NEED-0004 — set at the hosting service and on the deployed instance in one move once the platform's interface says where; not needed for `taktusctl run` |
| **A credential an assignment references** | what a `worker` step's execution unit is given at runtime, under the name the assignment carries — `VCS_TOKEN` for a repository token, a signing key. The process defines the name; the unit reads the value under it (`contracts/worker/v1` §3) | whatever the unit's task needs and no more; the process names the credential, so the permission is the process's declaration | the source system's schedule; the unit stores nothing, so a rotation is a change of the file the operator maps | configuration key `credential.<name>` — a file whose path is in `TAKTUS_CREDENTIAL_<NAME>_FILE`, read by the execution adapter at the moment a unit is started and injected into the unit: as its environment (`process`, `container`) or as a file in memory (`container`). For a worker configured by endpoint, whoever starts the worker puts the value into its environment under the name | the need of the credential the process names; NEED-0001 for `coding_credential` of the dev-orchestration blueprint |
| **Coding agent API key** | what the coding worker's agent authenticates with in `api-key` mode, referenced as `CODING_AGENT_API_KEY` (or the name `--credential` gives) | the agent's own account: usage billed to it, nothing else | the provider's policy; at once when it may have been seen | as the row above: `TAKTUS_CREDENTIAL_CODING_AGENT_API_KEY_FILE` for a launched unit, the environment for an endpoint worker; `tools/first_run.sh` takes the file's path from `CODING_AGENT_API_KEY_FILE`. The worker hands it to the agent under the agent's own variable and never logs it (`workers/claudecode/README.md`) | NEED-0001 |
| **Coding agent subscription token** | the same, in `session` mode: the long-lived token the agent's `setup-token` command issues for a subscription, referenced as `CODING_AGENT_SESSION` | the subscription's window; nothing else | when it expires or may have been seen; a session that expires mid-run halts the assignment at its last boundary, and a new token resumes it | as the row above, `TAKTUS_CREDENTIAL_CODING_AGENT_SESSION_FILE`; `tools/first_run.sh` takes the file's path from `CODING_AGENT_SESSION_FILE` | NEED-0001 |
| **Model API key** | the bearer credential the model endpoint `llm` steps ask (`TAKTUS_MODEL_ENDPOINT`) requires, if it requires one; a local model server needs none | the endpoint's own account: usage billed to it, nothing else | the provider's policy; at once when it may have been seen | configuration key `credential.model_api_key` — a file whose path is in `TAKTUS_CREDENTIAL_MODEL_API_KEY_FILE`, read through the configuration port when the model adapter is built and revealed only into the request header; masked in the startup log (`src/taktus/adapters/driven/models/`) | NEED-0003 |
| **Telemetry endpoint headers** | what the OTLP endpoint that collects the spans needs — an authorisation token, typically — as `name=value` pairs separated by commas | write to that endpoint's traces; nothing else | the platform's policy | configuration key `otlp.headers` — a file whose path is in `TAKTUS_OTLP_HEADERS_FILE`; masked in the startup log | none — optional; no process depends on telemetry being exported, and no collector has been chosen. A need is raised when one is |
| **CI read token** | lets the secret scan in the repository's own CI read the commits of a pull request | read access to the repository's pull requests; nothing else | none needed: the CI service creates it per workflow run and revokes it when the run ends; it is never stored | the workflow (`.github/workflows/ci.yml`, step `secrets`) receives it from the CI service; no operator supplies it | none — the CI service creates it per run; nobody supplies it |

The conformance gate and the connector tests hand random values to the reference connector and
to the fake of its service (`FAKE_REPOSITORY_TOKENS`) for the length of one test; they are
generated in the test, never committed, and the tests fail if one appears in an answer or a log.
The coding worker's gate does the same under `CODING_AGENT_API_KEY` and `CODING_AGENT_SESSION`
with a stand-in for the agent, and the container adapter's tests hand random values through
`TAKTUS_CREDENTIAL_*_FILE` files and check from inside the job that they are on no filesystem,
in no recorded configuration and in no log.

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
