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

| Parameter | What it is for | Permissions it needs | Rotation | How an operator supplies it |
|---|---|---|---|---|
| **Database connection** | how an instance reaches its PostgreSQL database. The whole URL is handled as a secret because it may carry the database password | a login that may connect to the instance's database, run the migrations, and use the application role the migrations create (`taktus_app`); nothing beyond that database (ADR-0020: one database per instance) | on the database's own schedule; changing the password on the server and the URL in the instance's configuration is one move | configuration key `database.url` — the environment variable `TAKTUS_DATABASE_URL` (read by the composition root through the configuration port, and by `make migrate` through `migrations/env.py`). The development database (`deploy/docker/compose.dev.yml`) has no password and trusts local connections only |
| **Repository access token of the requesting identity** | what the reference repository connector acts with when it reads an issue, opens a pull request, comments, or triggers a pipeline. It is **the requesting identity's** token with that identity's scopes; the connector has none of its own (`contracts/connector/v1` §5) | the requesting identity's permissions in the repository, and no more: read issues and pull requests, write pull requests and comments, trigger pipelines — whichever the process actually uses. The source system's permissions remain in force through it | whenever the hosting service's policy says, and at once when the identity leaves or the token may have been seen; revoke at the hosting service and issue a new one for the same identity | referenced **by name** in every call's context; the connector's runtime — whoever starts the connector — makes the value available under that name, in its environment or as a file it can read, before the call (`src/taktus/adapters/driven/connectors/github/README.md`). The connector reads it at the moment of the call and keeps nothing |
| **Webhook signing secret** | the secret the hosting service signs webhook deliveries with; the connector refuses every delivery it cannot verify against it, before the body is read (`contracts/connector/v1` §7) | none — it is a shared secret, not an account. It must be the same on both sides | when the hosting service's policy says, or when it may have been seen; set the new secret on the webhook at the hosting service and in the connector's environment in one move, after which deliveries signed with the old one are refused | the name the connector's declaration lists under `credentials` with purpose `intake`; the connector reads the value from its environment under that name at the moment of each delivery |
| **CI read token** | lets the secret scan in the repository's own CI read the commits of a pull request | read access to the repository's pull requests; nothing else | none needed: the CI service creates it per workflow run and revokes it when the run ends; it is never stored | the workflow (`.github/workflows/ci.yml`, step `secrets`) receives it from the CI service; no operator supplies it |

The conformance gate and the connector tests hand random values to the reference connector and
to the fake of its service (`FAKE_REPOSITORY_TOKENS`) for the length of one test; they are
generated in the test, never committed, and the tests fail if one appears in an answer or a log.

## Rule for every session in this repository

Never ask for a secret value. Write configuration that references a parameter — by configuration
key or by the name a call names — describe the parameter here, and tell the operator which
secret to create. Never write a deployment's name for a secret into this repository: the
operator's mapping from parameter to secret is theirs.
