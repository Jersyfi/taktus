# Credentials

**This register lists names, purpose, where a secret is used and how to rotate it — never values.**

The repository is public. No secret value, token, key or private certificate ever enters this
history, a file, a log or a message. A finding is handled as: rotate first, clean up second.

Configuration references secret *names*. The operator creates the secrets.

| Name | Purpose | Used in | Rotation |
|---|---|---|---|
| `GITHUB_TOKEN` | lets the secret scan in CI read the commits of a pull request | `.github/workflows/ci.yml`, step `secrets` | none needed: GitHub creates it per workflow run and revokes it when the run ends; it is never stored |
| `REPOSITORY_TOKEN` | the token the reference repository connector acts with — the **requesting identity's** token, with that identity's scopes; the connector has none of its own | referenced by name in every call's context (`contracts/connector/v1`), read by the connector at the moment of the call from its environment or a file, kept nowhere (`src/taktus/adapters/driven/connectors/github/`) | revoke the token at the hosting service and issue a new one for the same identity; nothing in Taktus stores it |
| `REPOSITORY_WEBHOOK_SECRET` | the secret the hosting service signs webhook deliveries with; the connector refuses every delivery it cannot verify against it | read by the connector's intake at the moment of each delivery | set a new secret on the webhook at the hosting service and in the connector's environment; deliveries signed with the old one are refused from then on |
| `TAKTUS_DATABASE_URL` | how an instance reaches its PostgreSQL database; carries the database password when the server requires one, which is why the whole URL is handled as a secret | the composition root (`src/taktus/composition/local.py`) through the configuration port; `make migrate` through `migrations/env.py` | change the database user's password on the server, then the URL in the instance's environment; the development database (`deploy/docker/compose.dev.yml`) has no password and trusts local connections only |

The conformance gate and the connector tests hand random values to the reference connector and
to the fake of its service (`FAKE_REPOSITORY_TOKENS`) for the length of one test; they are
generated in the test, never committed, and the tests fail if one appears in an answer or a log.

## Rule for every session in this repository

Never ask for a secret value. Write configuration that references a name, add the name here, and
tell the operator which secret to create.
