# Credentials

**This register lists names, purpose, where a secret is used and how to rotate it — never values.**

The repository is public. No secret value, token, key or private certificate ever enters this
history, a file, a log or a message. A finding is handled as: rotate first, clean up second.

Configuration references secret *names*. The operator creates the secrets.

| Name | Purpose | Used in | Rotation |
|---|---|---|---|
| `GITHUB_TOKEN` | lets the secret scan in CI read the commits of a pull request | `.github/workflows/ci.yml`, step `secrets` | none needed: GitHub creates it per workflow run and revokes it when the run ends; it is never stored |
| `TAKTUS_DATABASE_URL` | how an instance reaches its PostgreSQL database; carries the database password when the server requires one, which is why the whole URL is handled as a secret | the composition root (`src/taktus/composition/local.py`) through the configuration port; `make migrate` through `migrations/env.py` | change the database user's password on the server, then the URL in the instance's environment; the development database (`deploy/docker/compose.dev.yml`) has no password and trusts local connections only |

## Rule for every session in this repository

Never ask for a secret value. Write configuration that references a name, add the name here, and
tell the operator which secret to create.
