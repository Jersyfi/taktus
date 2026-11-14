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

The gate is the secret scan, `make gate-secrets` locally and `tools/scan_secrets.sh` in CI's lane
`static`. Its rule `generic-api-key` looks at every value beside a word such as `key`, `token` or
`secret`, and reports one whose entropy is high. In `tests/fakes/cloud_service.py` it would have
caught a token or a private key written into the fake by mistake.

On the one value the exception names it can catch nothing: `KEY_ALG_RSA_2048` is the name the
published identity interface gives an algorithm, the same for every key, and it opens nothing.
The single finding of the pull request was that value, in that file, beside the word
`keyAlgorithm`. The fake no longer carries it; one commit of the branch's history does.

Everywhere else the scan looks exactly as before. Before the exception, `tools/scan_secrets.sh
origin/main HEAD` reported that one finding; after it, none; the same value in another file, and
any other value in this file, are still judged by the rule, and the planted key the script proves
itself with before every scan is still found.
