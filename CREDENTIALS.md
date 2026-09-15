# Credentials

**This register lists names, purpose, where a secret is used and how to rotate it — never values.**

The repository is public. No secret value, token, key or private certificate ever enters this
history, a file, a log or a message. A finding is handled as: rotate first, clean up second.

Configuration references secret *names*. The operator creates the secrets.

| Name | Purpose | Used in | Rotation |
|---|---|---|---|
| `GITHUB_TOKEN` | lets the secret scan in CI read the commits of a pull request | `.github/workflows/ci.yml`, step `secrets` | none needed: GitHub creates it per workflow run and revokes it when the run ends; it is never stored |

## Rule for every session in this repository

Never ask for a secret value. Write configuration that references a name, add the name here, and
tell the operator which secret to create.
