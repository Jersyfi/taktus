# ADR-0203 — A secret store's metadata is read, and never its value

**Status:** accepted · extends ADR-0187 (a secret store fills the files Taktus reads) and
ADR-0196 (what expires) · serves UC-03 B-1.09, B-1.10, UC-7.3 · issue #447

## Context

UC-03 B-1.10 asks that a secret due for rotation be identified and its rotation prepared, while
triggering it stays with a person. B-1.09 asks that signing certificates and provisioning
profiles be listed before they expire. Both were unbuilt: no generic interface reads a secret
store's metadata, and no open standard publishes when a signing credential expires.

ADR-0187 decided that the operator's secret store fills the files Taktus reads, outside Taktus.
Taktus never holds a store's credential that could read a value, and it never writes one.

The stores the most businesses use publish their metadata apart from their values: Google
Secret Manager lists secrets and their versions, AWS Secrets Manager answers `ListSecrets`,
and HashiCorp Vault's key-value engine version 2 has a metadata path beside its data path. The
App Store Connect API lists a team's signing certificates and provisioning profiles with their
expiration dates.

## Decision

### 1. `secrets.metadata`: when each secret last changed

`secrets.metadata.list` answers, per secret, its name, when it was created and when its
current value was set, the whole days since, what the store states about rotation, its expiry
and when it was last read. The oldest change comes first. Three connectors serve it: `gcp`
(Secret Manager), `aws` (Secrets Manager) and `vault` (key-value version 2).

### 2. No value is ever read

No connector calls an endpoint that returns a value: not Secret Manager's `access`, not
`GetSecretValue`, not Vault's `data` path. Each connector's README names the endpoints it never
calls, and its tests assert that none was requested. The credential an operator gives it needs
the permission to list metadata alone.

### 3. A rotation is proposed, never triggered

B-1.10 files an issue for the secret whose value is oldest past the tenant's age. The issue
names the secret, its age and the steps. Rotating it is the operator's act in the store, which
then fills the files as ADR-0187 says. Taktus changes nothing in the store.

### 4. `expiry.credentials`: a team's signing credentials

`expiry.credentials.list` answers each signing certificate and provisioning profile with its
type, platform, state, expiration and whole days left, and a key that names it and its moment
(ADR-0196 §1). The `appstore` connector serves it, signing its requests with the team's API key
as the provider's documentation prescribes. A certificate's or profile's content is never asked
for. A development certificate names the person it was issued to, so its name is never read:
the serial number stands for it (principle 14).

## Alternatives

- **Read the value and judge its age from it.** A value carries no age, and reading it would
  give Taktus what ADR-0187 keeps outside it.
- **Rotate through the store's own rotation.** AWS Secrets Manager rotates by a function the
  operator writes. Triggering it is the act UC-03 keeps with a person.
- **List the consumers of a secret.** No store answers who reads a secret. The files the
  operator's store fills are named in its own configuration, outside Taktus.

## Consequences

- Three new connectors, `gcp`, `vault` and `appstore`, and the `aws` connector serving
  `secrets.metadata`; each with a fake of the store's published interface.
- B-1.10 is built; B-1.09 reads the signing credentials too.

## Where this promise ends

- **The age is the store's statement.** A value replaced outside the store, or a store that
  keeps no version moments, gives no age.
- **Every consumer is not listed.** UC-03 B-1.10 asks for it; no store states it.
- **Vault's key-value engine has no rotation.** Its `rotation` is null. Other Vault engines,
  dynamic secrets among them, are not read.
- **One team of the app store.** A business with several teams configures one connector each.
- **Nothing is renewed.** Renewing a signing certificate needs a new signing request from the
  business's key, which stays with a person.
