# Catalogue contract v1

A **catalogue** is an index over signed images and bundles. An operator finds adapters and
process bundles in it; an instance verifies an entry and installs it. The index runs no code:
each entry names one artifact by its digest and is signed over its own content. Why it is built
this way is ADR-0175; what it must achieve is UC-14.6.

| File | Contents |
|---|---|
| [`Catalogue.json`](Catalogue.json) | the index, the entry, the signature and the file of trusted keys, as JSON Schema 2020-12 |
| [`examples/`](examples/) | valid and must-fail examples per definition |

`make gate-contracts` checks the schema and every example.
`tests/contract/test_catalogue_binding.py` holds the core's binding to it: every valid example
reads into the catalog component's model, and every signature in them verifies.

---

## 1. The index

An index has a name, `catalogue`, and its `entries`. An entry has a `kind`:

- `image` — an adapter's image. It names the `image` without a tag, its `digest`, the `family`
  (`worker`, `connector` or `model`), the `contract` it implements, as `connector/v1`, and the
  `capabilities` it serves. The operator's deployment pulls it by digest.
- `bundle` — a process bundle. It names the `process`, the `bundle` file relative to the index
  and below its directory, and the `digest` of the file's bytes.

## 2. The tiers

An entry states the tier of its publisher:

| Tier | Meaning |
|---|---|
| `reference` | kept by the Taktus project |
| `community` | signed by its author; `experimental`, at autonomy level 2 or below until verified |

*Verified* is the third tier, and no index states it. The instance derives it: an installed
adapter is verified when its conformance suite and its removal test both passed in the
instance's own configuration after the entry was installed (ADR-0044, ADR-0175 §5). An entry
whose tier is `verified` fails the schema.

## 3. The signature

The signature covers the entry without its `signature` field, serialised as canonical JSON:
object keys sorted, no whitespace between tokens, UTF-8 without escaping. In Python:
`json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`. The scheme is
Ed25519; the key and the value are base64url without padding. Because the entry carries the
artifact's digest, the signature binds the artifact.

`taktusctl catalogue sign INDEX --seed-file FILE` fills each bundle's digest from its file and
signs every entry. `taktusctl catalogue key --seed-file FILE` prints the public key. The seed
is thirty-two bytes, read from the file and never printed.

## 4. The trusted keys

The file `TAKTUS_CATALOGUE_KEYS` names lists every key the operator trusts, with the one tier it
may sign and the author it stands for. An entry is admitted only when its key is listed for the
tier the entry states and its signature verifies. A community key cannot sign a reference entry.
Public keys are no secret.

## 5. What it is not

Not a store: nothing is paid for. Not the marketplace of `docs/vision/beyond-1.0.md`. The
project's own community tier opens with the licence (DEC-0044) and the contributor agreement.
