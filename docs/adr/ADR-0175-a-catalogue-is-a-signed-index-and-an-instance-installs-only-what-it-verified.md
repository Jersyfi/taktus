# ADR-0175 — A catalogue is a signed index, and an instance installs only what it verified

**Status:** accepted · extends ADR-0044 (the instance measures the conformance half itself) and
ADR-0039 (from level 3 a step runs only on a verified adapter) · roadmap `1.0.0`; UC-14.6,
issue #348

## Context

From `1.0.0` community adapters live in repositories of their own (ADR-0009). An operator then
needs a way to find them, and to know who published what. DEC-0190 accepted a catalogue in three
tiers for this (F8): *reference*, kept by the project; *verified*, passed in the instance's own
configuration; *community*, signed by its author and held at level 2 until verified. UC-14.6
states it.

Five questions had to be answered. What is a catalogue, physically? What is signed, and with
what? Whom does an instance trust? What does "install" mean for an image, which the instance
does not run itself, and for a bundle? How does a community entry stay at level 2?

## Decision

### 1. A catalogue is an index file, by contract

A catalogue is a JSON document, `contracts/catalogue/v1/Catalogue.json#/$defs/Index`: a name
and a list of entries. An entry names one artifact. An **image** entry names the image, its
digest, the adapter family, the contract it implements and the capabilities it serves. A
**bundle** entry names the process, the bundle's file beside the index and the digest of its
bytes. Each entry states its tier, `reference` or `community`, and nothing else: an index that
states `verified` is refused by the schema. The instance reads the index files in the directory
`TAKTUS_CATALOGUE_DIRECTORY` names, on each request, as the gallery reads its own (ADR-0136).
It fetches nothing and starts nothing.

### 2. Each entry is signed over its own content, with Ed25519

The signature covers the entry without its `signature` field, as canonical JSON: keys sorted,
no spaces, UTF-8. The entry carries the artifact's digest, so the signature binds the artifact.
The scheme is Ed25519, which the instance already verifies submissions with (ADR-0118). An
author signs with `taktusctl catalogue sign`, which reads the seed from a file and fills each
bundle's digest from its bytes; `taktusctl catalogue key` prints the public key. No key is ever
printed but the public one.

### 3. The operator names the keys it trusts, per tier

`TAKTUS_CATALOGUE_KEYS` names a file of trusted keys (`#/$defs/Trust`): each public key with the
tier it may sign and the author it stands for. An entry is admitted only when its key is listed,
for the tier the entry states, and its signature verifies. A community key cannot sign a
reference entry. Public keys are no secret; the file is configuration.

### 4. Installing records the entry, and makes what the instance itself would make

`taktusctl catalogue install` verifies the entry again, then:

- for an **image**, it binds the entry to the adapter identifier the operator names, of the
  entry's family (`connector.mail` for a connector), and prints the image by digest for the
  operator's deployment to pull. The deployment starts it; the instance never does;
- for a **bundle**, it checks the bundle's bytes against the digest and parses it as
  registration does. A community bundle above level 2 is refused. The bundle becomes a
  proposal (ADR-0091), and a person decides on it as on any other.

One transaction then writes the record `CatalogueInstallation` — the index, the entry as it was
verified, its author, the identifier or the proposal, who installed it and when — and the
ledger entry `catalogue.installed`: the entry's tier as `outcome`, the identifier as `adapter`
or the proposal's version in `refs.process_version`, the person in `refs.actor`, and the digest
of the stored evidence in `content_digest`. Migration 0096 adds the table.

### 5. *Verified* is derived, and a pass before the installation does not count

The tier an entry has in the instance is derived, never stated. An installed adapter is
*verified* when its maturity record is (ADR-0044): both halves passed for the configuration
that resolves its identifier now. A conformance pass or a removal test taken before the entry
was installed is not counted: it was taken on what stood behind the identifier before. The run's
maturity port answers from this rule, so a step at level 3 refuses an adapter installed from the
catalogue until it is verified after its installation. A community adapter is therefore held at
level 2 by the gate that already holds every experimental adapter there (ADR-0039).

## Alternatives

- **Keyless signatures through a public transparency log.** They prove an identity at a
  provider, need a network call and a new dependency to verify, and tie an instance to that
  provider. An image is signed that way by its workflow (#347); an entry is a document the
  operator verifies offline.
- **A catalogue served over HTTP by the instance.** The instance would reach outward for its own
  configuration, which the adapter obligation keeps to adapters. The operator fetches an index
  as he fetches an image.
- **Let a reference entry count as verified.** *Reference* says who keeps it, not that it
  conforms in this configuration (ADR-0044).
- **A level cap stored on the installation.** The level-3 gate already holds every adapter that
  is not verified. A second cap would be a second place where a level is set (ADR-0039).
- **Record refused installations in the ledger.** A refusal changes no state; the command
  answers it with every reason. Recording it would add a kind for nothing that happened.

## Consequences

- `contracts/catalogue/v1`: the index, the entry, the signature and the trust file.
- `catalog`: `domain/model/catalogue.py`, `domain/service/catalogue.py` (the signed payload, the
  admission, the count after installation), `ports/signatures.py`,
  `application/service/catalogue.py` (`CatalogueInstalls`, the one writer of the record).
- `composition/catalogue.py` reads the indexes and the trust file, and makes the proposal;
  `composition/maturity.py` counts a pass only after the installation.
- `taktusctl catalogue list | install | sign | key`; `TAKTUS_CATALOGUE_DIRECTORY`,
  `TAKTUS_CATALOGUE_KEYS`; migration 0096.

## Where this promise ends

A signature says who published an entry. It says nothing about whether the artifact is good,
safe or free of vulnerabilities: the image's scan and its own signature are #347's, and the
operator's deployment checks them when it pulls. The instance does not check that the image the
deployment runs is the digest it printed; it checks the declaration and the conformance of what
answers behind the identifier. A key the operator trusts and later distrusts does not uninstall
what it signed: the record keeps its origin, and the operator removes it. Installing a bundle
writes the proposal first and the record after; a failure between them leaves a proposal
without a record, which a person sees and may reject. A bundle has no conformance suite: above
level 2 it runs only as a person's own governed proposal, whose steps from level 3 run only on
verified adapters. The project publishes no index of its own yet: its reference index is a
release artefact, and its community tier opens with the licence (DEC-0044) and the contributor
agreement.
