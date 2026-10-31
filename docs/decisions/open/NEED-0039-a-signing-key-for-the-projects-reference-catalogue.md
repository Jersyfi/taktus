# NEED-0039 — A signing key for the project's reference catalogue

**Kind:** credential
**Raised in:** the branch `concept/package-d` (package D, built in concept mode, DEC-0222), for issue #348
**Issue:** [#658](https://github.com/Jersyfi/taktus/issues/658)
**Needed by:** before the first release that ships the project's reference index (M3.6)
**Foreseeable since:** the branch `concept/package-d--catalogue`, where an instance began to install only catalogue entries signed by a key it trusts (ADR-0175)

## 1. What is needed

One Ed25519 key of the project: a seed of 32 random bytes that signs the entries of the
project's reference index. You generate it. Nobody provides it from elsewhere. Its public half
is published with the release, so that an operator can trust it for the tier *reference*.

## 2. Why

An instance installs a catalogue entry only when a key it trusts for the entry's tier signed it
(ADR-0175, UC-14.6). The mechanism is built and tested with test keys. The project's own
reference index — the adapters and bundles Taktus keeps — is a release artefact signed when a
release is cut. Without the project's key no operator can tell a reference entry from anyone
else's.

## 3. By when

**Before the first release that ships the reference index.** Preparing a release is yours
(M3.6), so the date follows yours. Until then nothing waits: operators install entries signed
with their own keys.

## 4. How to provide it

**Step 1 — the seed.** On your machine, write 32 random bytes into a file only you can read:

```sh
umask 077 && openssl rand 32 > "<path of the seed file>"
```

**Step 2 — the public key.** `taktusctl catalogue key --seed-file "<path of the seed file>"`
prints the public key. Paste it into the issue; the public key is not a secret.

**Step 3 — the release.** Put the seed file into the secret store of the environment the release
workflow will name, as the parameter `catalogue.signing_seed`. The session that builds the
release step reads it from there through `TAKTUS_CATALOGUE_SIGNING_SEED_FILE` and never prints
it.

**Rotation:** a new seed, its public key published, and the old key withdrawn from the trusted
keys at once when the seed may have been seen. Entries signed with the old key are signed again.

## 5. What it must never be

- **Never a key used for anything else**, such as the images' signature (keyless, ADR-0173) or
  a deployment key.
- **Never in this repository**, a chat, an issue or a variable a process listing shows. Only the
  public half leaves your machine.

## 6. What happens next

Write in the issue: **"NEED-0039 is provided."** The next session records it first, adds the
public key to the documentation of the reference tier, and builds the release step that signs
the reference index.

## 7. How to confirm

`taktusctl catalogue list` on an instance that trusts the published key for *reference* shows
the project's entries as admitted.
