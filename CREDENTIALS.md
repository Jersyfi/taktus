# Credentials

**This register lists names, purpose, where a secret is used and how to rotate it — never values.**

The repository is public. No secret value, token, key or private certificate ever enters this
history, a file, a log or a message. A finding is handled as: rotate first, clean up second.

Configuration references secret *names*. The operator creates the secrets.

| Name | Purpose | Used in | Rotation |
|---|---|---|---|
| *(maintained from `0.1.0`)* | | | |

## Rule for every session in this repository

Never ask for a secret value. Write configuration that references a name, add the name here, and
tell the operator which secret to create.
