# NEED-0041 — A password-manager service account for Taktus

**Kind:** account
**Raised in:** the session that builds package D, on 2026-10-31, for DEC-0224
**Issue:** [#662](https://github.com/Jersyfi/taktus/issues/662)
**Needed by:** before #660, which lets the instance take its secrets from a secret store
**Foreseeable since:** DEC-0224, where the owner decided that Taktus may have a 1Password service account of its own

## 1. What is needed

A second 1Password service account, for Taktus's own instance and for nothing else. It only
reads, and only the secrets the instance itself uses: the keys `CREDENTIALS.md` lists for the
instance, such as the coding agent's key and the repository token.

The recommended shape is a vault of its own for those secrets, with this account granted read
access to that vault alone. A service account is granted whole vaults, not single items. If it
shared `Development`, it could read the session's secrets too, which is more than the instance
needs. If you prefer one vault, grant this account read access to `Development` only.

## 2. Why

DEC-0224: Taktus may have a service account of its own, separate from the session's, so that
either can be withdrawn alone. Today the instance's secrets are written into the cluster by hand
at install. With the account, they come from one place, and rotating one means changing it once.
How Taktus reads them — at install into the files it already reads, or at run time through an
adapter — comes as an ADR with its own issue first.

## 3. By when

**Before #660 is built.** Nothing waits
before then, and the instance keeps running on the files it has.

## 4. How to provide it

**Step 1 — the vault.** In 1Password, create a vault for the instance's secrets. The session
names the items it should hold when the ADR is written.

**Step 2 — the account.** Create a service account with read access to that vault only. Give it
a name that says what it is for, such as "Taktus instance".

**Step 3 — the token.** Do not put the token into a file for the session. The session writes the
steps that put it into the instance's secret store when the ADR says where it belongs. Until
then, keep it in 1Password.

**Rotation:** a new token in 1Password, then the same step 3 again. The old one is revoked at
once when it may have been seen.

## 5. What it must never be

- **Never the session's service account** (NEED-0040), and never an account that can write.
- **Never in this repository**, a chat, an issue or an environment variable that a process
  listing shows.

## 6. What happens next

Write in the issue: **"NEED-0041 is provided."** The next session records it first, writes the
ADR for how the instance reads its secrets, and names the items the vault is to hold.

## 7. How to confirm

1Password shows the service account with read access to one vault, and the session's own
service account has none to that vault unless you granted it.
