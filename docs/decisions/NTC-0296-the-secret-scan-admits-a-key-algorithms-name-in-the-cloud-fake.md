# NTC-0296 — The secret scan admits a key algorithm's name in the cloud fake

**Mode entry:** M2.3
**Kind:** gate-weakened
**Decided:** 2026-11-14
**Raised in:** the branch `concept/package-f` (package F, DEC-0239)

## 1. What was decided

`.gitleaks.toml` gains a third exception to the rule `generic-api-key`. A finding is set aside
only when both hold: the file is `tests/fakes/cloud_service.py`, and the value found is exactly
`KEY_ALG_RSA_2048`.

## 2. The evidence

- The fake of the cloud's identity interface listed a service account key as the published
  interface does, with the field `keyAlgorithm` and the value `KEY_ALG_RSA_2048`. gitleaks'
  generic rule reported it in CI's lane `static` on the pull request of package F.
- The value is the name of an algorithm from the published API reference, the same for every
  key; it identifies nothing and opens nothing.
- No reader uses the field, so the fake no longer carries it. The scan reads every commit of the
  branch, and one commit of its history still holds the value; the exception is for that commit.

## 3. What was considered

- **Rewriting the branch's history.** Rejected: the branch is shared by the package's areas, and
  history is not rewritten on a shared branch.
- **A fingerprint in `.gitleaksignore`.** Rejected for the reason NTC-0259 gives: a squash merge
  makes a new commit.
- **Setting the file aside as a whole.** Rejected: a real token written into the fake would pass.

## 4. Which entry permits it

M2.3 of `docs/decisions/anchors.taktus.md`, as for NTC-0259: the exception narrows what the gate
looks at, and section 5 is the demonstration.

## 5. Why the gate had no value

On this one value in this one file the rule can find nothing but the name of an algorithm. The
same value in any other file is still found, and any other value in this file is still judged by
the rule as before. The planted key `scan_secrets.sh` proves itself with is still found.
