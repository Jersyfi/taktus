# ADR-0269 — A function built from an uploaded source is a hosted version, under `deployment.sites`

**Status:** accepted · extends ADR-0211 (a deployment target that is not a cluster) and ADR-0024
(idempotency) · UC-03 §4.8, §8 "deployment targets with rollback", DEC-0228

## Context

ADR-0211 split targets that are not a cluster into two shapes. A **serverless workload** runs a
container image as a revision (`deployment.workloads`). A **hosted site** publishes a version the
business's own build uploaded, and puts an earlier one back by naming it (`deployment.sites`).
The most widely used serverless functions platform fits neither name exactly. A function has no
image and no container: the platform builds it from a source archive the business's build
uploaded. It keeps only the source it was last built from.

## Decision

### 1. A function serves `deployment.sites`

The function's shape is the hosted site's: a version uploaded, put live, and an earlier version
named and put back. A connector `cloudfunctions` serves `deployment.sites.read`, `.release` and
`.rollback` with the inputs and outputs of the site connectors, under `SITES_TOKEN`. A version
is the archive, `<bucket>/<object>#<generation>`, with its generation, so that one name means
one archive for good. `rolled_out` is the function `ACTIVE` and built from the version named.
The capability's name stays. Its meaning is a hosted version, which a site and a function both
are.

### 2. The key is a label of the function

A release and a rollback patch the function's source and its labels. The label `taktus-key`
carries a digest of the idempotency key. A repeat that finds the label is `replayed`. A function
already deploying is a `conflict` before anything is written.

### 3. Both release processes run on it

B-8.05's site version runs unchanged. B-8.06 gains a version for a hosted target,
`B-8.06-hosted-deployment.yaml`, of the same process `b-8-06`. It reads the live version first,
so that the rollback can name it, then releases, waits for `rolled_out`, watches the error rate
for thirty minutes and puts the rollback to a person on a rise. A tenant registers the version of
its target (ADR-0191).

## Alternatives

- **`deployment.workloads`.** Its release sets a container's image. A function has neither, and
  an archive passed as an image would mean something else under the same input.
- **A third capability for functions.** Its three operations would be the site's, word for word,
  and B-8.05's site version could not run on it.
- **The platform's underlying container service.** It is reached through `cloudrun`, but a
  function deployed by its own API would be changed behind it.

## Consequences

- Connector `cloudfunctions`, its fake `tests/fakes/functions_service.py`, scenario and image;
  `SITES_TOKEN` names it in `CREDENTIALS.md`, a service account key with Cloud Functions
  Developer and Service Account User.
- B-8.05's site version and B-8.06's hosted version are proven against it
  (`tests/composition/test_software_operations_connectors2.py`).

## Where this promise ends

- **The mark is one label.** A repeat after a write under another key replaced it acts again.
- **A label set by somebody else between the reading and the write is lost.** The function has
  no `etag`, so the patch cannot be held to what was read.
- **The archive is not checked.** The connector reads no storage. An archive that does not build
  never becomes `rolled_out`, and the wait hands the run to a person.
- **A rollback needs the earlier version named.** The function keeps no history of its sources.
- **No canary, no traffic split** (ADR-0211).
- **The fake follows the published reference.** How the API answers a patch during a deployment
  is not documented, and the connector never sends one; nothing was run against the platform.
