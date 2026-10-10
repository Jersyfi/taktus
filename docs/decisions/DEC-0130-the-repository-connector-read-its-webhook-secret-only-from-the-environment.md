# DEC-0130 — The repository connector read its webhook secret only from the environment

**Category:** DEFECT
**Raised in:** the pull request that deploys the repository connector with the chart, for issue #66
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

CLAUDE.md §9 and `CREDENTIALS.md` say a secret value is read from a file the variable
`TAKTUS_<KEY>_FILE` points at, never from the environment, and the chart mounts every secret as
such a file. The repository connector read the webhook signing secret only from the variable
`REPOSITORY_WEBHOOK_SECRET`, and a credential an action references with `injected_as: env` only
from the variable of its name. On the cluster the connector could therefore not be given its
webhook secret without breaking the rule, and every delivery would have been refused. The chat
connector already followed the pattern.

## 2. Why you are being asked

You are not. Code and register contradicted the doctrine, a documentation defect corrected under
entry M1.4.

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

- The connector now reads such a value from the file `TAKTUS_CREDENTIAL_<NAME>_FILE` names, and
  from the variable of the name only when no file is named — as the chat connector does.
- It is read at each call, so a rotated file is used by the next delivery without a restart. A
  test shows both.
- The connector's README and the register's row for the webhook secret say so.

## 5. Options

None for the owner.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0130" in an issue.

## Outcome

**Corrected:** 2026-10-10
**What was wrong:** the repository connector read its webhook secret, and an env-injected credential, only from an environment variable.
**Why it was wrong:** it was written before the one pattern for every credential variable (DEC-0018) reached the connectors.
**What it now says:** the file `TAKTUS_CREDENTIAL_<NAME>_FILE` names comes first, the variable only without one.
**What changed in substance:** the connector can run on the cluster with its secrets as mounted files.
**Recorded in:** this pull request
