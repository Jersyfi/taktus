# Examples and conformance fixtures

`make gate-contracts` validates everything here against the schema.

## Layout

```
examples/<definition>/valid/<name>.json          validates against Connector.json#/$defs/<Definition>
examples/<definition>/invalid/<name>.json        must fail
examples/<definition>/invalid/C-NN-<name>.json   must fail, and is the fixture for conformance check C-NN
```

The directory name is the definition in kebab-case: `call-context` is `CallContext`,
`intake-result` is `IntakeResult`.

## What each check's fixture shows

| Check | Fixture | What the schema refuses |
|---|---|---|
| C-01 | `capabilities/invalid/C-01-…` | a declaration without a capability |
| C-02 | `operation/invalid/C-02-…`, `effect-report/invalid/C-02-…`, `result/invalid/C-02-…` | an outward operation without idempotency; an outward effect without a record; a result without an effect |
| C-03 | `capabilities/invalid/C-03-…` | permissions other than `passthrough` |
| C-04 | `call-context/invalid/C-04-…` | a credential with a value in the context |
| C-05 | `effect-report/invalid/C-05-…` | an outward effect that does not say whether it was replayed |
| C-06 | `error/invalid/C-06-…` | a bare message instead of an Error |
| C-07 | `intake/invalid/C-07-…` | an intake command without a reply address |
| C-08 | `intake-declaration/invalid/C-08-…`, `refusal/invalid/C-08-…` | an intake without signature verification; a refusal reason outside the vocabulary |
| C-09 | `result/invalid/C-09-…` | a result without consumption |
| C-10 | `capabilities/invalid/C-10-…` | a product name where a capability belongs |

The schema fixes the shape. The behaviour behind each check — a repeat recognised, a signature
refused, a credential absent from a log — is what the suite proves against a live connector,
and what `tests/conformance` proves the suite catches (`CONFORMANCE.md` §8).

## Placeholders

Identifiers, digests, URLs and hosts are invented (`repo.example`, `placeholder-…`). Credential
names are names only; no example carries a value, and the one file that does (`C-04`) exists to
fail. Header names in the intake examples are generic; a real connector's scenario names its
target's.
