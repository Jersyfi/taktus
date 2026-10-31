# NEED-0040 — The session's password-manager token on its machine

**Kind:** credential
**Raised in:** the session that builds package D, on 2026-10-31, for DEC-0224
**Issue:** [#661](https://github.com/Jersyfi/taktus/issues/661)
**Needed by:** 2026-11-07
**Foreseeable since:** DEC-0224, where the owner decided that the session reads secrets from 1Password through a service account of its own

## 1. What is needed

The token of the 1Password service account you hold for the session, in a file on the machine
the session runs on, readable only by your user. The service account needs access to the vault
`Development`: to read its items, and to write new ones, so that the session can generate a
random value straight into the vault instead of asking you to.

## 2. Why

DEC-0224: secrets are kept in 1Password, and the session reads them through its own service
account. Without the token the session can only ask you for every value, file by file, as
before. With it, two open needs shrink to granting access: the connect key (NEED-0037) and the
catalogue's signing seed (NEED-0039) are random values the session can generate into the vault.

## 3. By when

**2026-11-07.** Nothing is blocked before then. Until it is there, every credential reaches the
session as it did before.

## 4. How to provide it

**Step 1 — the access.** In 1Password, give the service account access to the vault
`Development` with the permissions to read and to write items.

**Step 2 — the file.** In a terminal on the machine, write the token into a file only you can
read. Paste the token from 1Password where the command waits, then press Ctrl-D:

```sh
umask 077 && cat > "<path of the token file>"
```

**Step 3 — the path.** Tell the session the path of the file in conversation. The path is not a
secret; the token is, and it never goes into a chat, an issue or this repository.

**Rotation:** a new token in 1Password, written into the same file. The old one is revoked in
1Password at once when it may have been seen.

## 5. What it must never be

- **Never the token of the service account Taktus uses** (NEED-0041). Each can be withdrawn alone.
- **Never an account with access beyond the vault `Development`.**
- **Never in this repository**, a chat, an issue or an environment variable that a process
  listing shows.

## 6. What happens next

Write in the issue: **"NEED-0040 is provided."** The next session records it first and checks the
access without printing a value: `op whoami` and `op vault list`, with the token handed to `op`
from the file. Then it rewrites the steps of NEED-0037 and NEED-0039 to what the session can now
do itself.

## 7. How to confirm

The session reports that `op vault list` through the service account names the vault
`Development`, and nothing more of the vault's contents.
