# NTC-0259 — The secret scan admits a public key in the catalogue's examples

**Mode entry:** M2.3
**Kind:** gate-weakened
**Decided:** 2026-10-31
**Raised in:** the branch `concept/package-d` (package D, DEC-0222), for issue #348

## 1. What was decided

The secret scan (`tools/scan_secrets.sh`, CI's lane `static`) runs gitleaks with its default
rules. It now reads a configuration, `.gitleaks.toml`, which keeps those rules and adds one
exception to the rule `generic-api-key`. A finding is set aside only when both of these hold:

- the file lies under `contracts/catalogue/v1/examples/`;
- the value found is exactly 43 characters of base64url, the length of an Ed25519 public key.

## 2. The evidence

- The catalogue contract (ADR-0175, `contracts/catalogue/v1`) names a signing key by its public
  half. Its examples carry such keys in a field `key`, and gitleaks' generic rule reported seven
  of them as secrets on the pull request of package D.
- A public key is published by design: an operator trusts an author by it. None of the seven is
  a seed. The seeds of the tests are made in the tests and never written to an example.
- The exception was tried on a throwaway repository with three files. The same 43-character
  value in a file outside the examples was found. A 47-character value inside the examples was
  found. Only the public key inside the examples was set aside. The planted key that
  `scan_secrets.sh` proves itself with before every scan is still found.

## 3. What was considered

- **A fingerprint in `.gitleaksignore`.** Rejected: a fingerprint names a commit, and a squash
  merge makes a new one, so the scan would fail on `main`.
- **Encode the keys so that the rule does not match.** Rejected: changing a contract's format to
  escape a scanner hides the meaning from a reader while satisfying the gate.
- **Set aside the examples' directory as a whole.** Rejected: a seed written there by mistake
  would pass unseen.

## 4. Which entry permits it

M2.3 of `docs/decisions/anchors.taktus.md`: weakening a gate only where it is demonstrated that
the gate has no value. An exception narrows what the gate looks at, so it is this entry, and
section 5 is the demonstration.

## 5. Why the gate had no value

The gate is the secret scan, `make gate-secrets` locally and `tools/scan_secrets.sh` in CI's
lane `static`. Its rule `generic-api-key` looks at every value beside a word such as `key`,
`token` or `secret`, and reports one whose entropy is high. It would have caught a seed or a
token written into the catalogue's examples.

On one kind of value it can catch nothing but a public key: a value of exactly 43 characters of
base64url inside `contracts/catalogue/v1/examples/`. The contract puts nothing else of that shape
there. A seed is 32 bytes as well, but the catalogue never writes a seed to a file of its own:
`taktusctl catalogue sign` and `key` read it from the file `--seed-file` names, outside the
repository. All seven findings of the pull request were that kind of value, and each was a public
key, one of the test keys the examples are signed with.

Everywhere else the scan looks exactly as before. The trial of section 2 shows it: the same value
in another file was found, and a longer value in the examples was found.
