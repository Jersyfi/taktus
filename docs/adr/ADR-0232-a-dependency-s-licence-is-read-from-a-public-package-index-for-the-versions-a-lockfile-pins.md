# ADR-0232 — A dependency's licence is read from a public package index for the versions a lockfile pins

**Status:** accepted · extends ADR-0150 (connectors for a business's systems) and ADR-0192
(the processes of software operations select by a rule) · UC-03 B-10.04, UC-01 P-10, DEC-0228

## Context

B-10.04 asks that the licence of every dependency be checked and every conflict reported. The
repository holds the manifest; it does not hold the licences of what the manifest names. The
repository service's own export of a bill of materials states licences, but its synchronous
endpoint is announced to be withdrawn on 13 November 2026 in favour of an asynchronous report.
A public package index, deps.dev, states for each version of a package the licences in SPDX
expressions, across the common package systems, without a key.

## Decision

### 1. A connector `packages.licences` reads a manifest's pinned versions

The connector takes the manifest's text and its format — npm's `package-lock.json`, uv's
`uv.lock`, pip's `requirements.txt` — and reads every exact version it pins, by each format's
own rules. It asks the index for each version, one request per version, and answers its
licences, whether it is a development dependency, and whether the index knows the version. A
requirement that pins no exact version is named as `unpinned`; a version is never guessed from
a range. Only a package's system, name and version leave the connector, never the manifest.

### 2. The manifest is read through the repository connector

The process reads the manifest with `repository.files.read` and hands its text to the licence
connector. The two adapters do not call each other; the run joins them.

### 3. Rules judge, the policy is the tenant's

Two `filter` rules judge the dependencies that are not only for development: a licence of a
named family is a conflict, and a version without a known licence, or with one that is no
standard expression, is named too. The families are the bundle's literals, a default; the
tenant sets its own policy in a version of its own. The tenant's corridor turns a conflict into
an incident. An exception stays with a person (UC-03 §6).

## Alternatives

- **The repository service's bill of materials.** Its synchronous export is being withdrawn,
  and it covers one repository service only.
- **A model reads the licence files.** A licence is a fact the index states; a model could read
  a restrictive licence as permissive.
- **Parsing the manifest in the run.** Each format's rules belong to an adapter, as each
  provider's shape does; the core sees one answer.

## Consequences

- The connector `depsdev/`, its fake `tests/fakes/package_index_service.py`, connector tests,
  a conformance entry, removal coverage, an image, `PACKAGES_TOKEN` in `CREDENTIALS.md`, which
  the contract requires (C-03) and the index never receives.
- `B-10.04-dependency-licences.yaml` in the blueprint `software-operations`.

## Where this promise ends

- **The licence is the index's statement**, not a reading of the package's own files; a
  version the index does not hold is `known: false`.
- **Three manifest formats.** Another ecosystem's lockfile is refused as `invalid`, not guessed.
- **The attribution file is not kept.** Writing it is a change of the repository, which the
  implementation process makes on a filed issue; its form is the business's own.
- **One request per version.** A lockfile of thousands of packages takes thousands of requests,
  and `limit` bounds a reading at 2000; above it the step stops rather than check part.
- **Proven against a fake of the published API** (DEC-0225).
