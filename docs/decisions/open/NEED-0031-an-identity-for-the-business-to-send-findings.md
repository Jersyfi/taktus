# NEED-0031 — An identity for the business to send findings

**Kind:** credential
**Raised in:** the pull request that closes [#446](https://github.com/Jersyfi/taktus/issues/446)
**Issue:** [#533](https://github.com/Jersyfi/taktus/issues/533)
**Needed by:** 2026-10-31
**Foreseeable since:** #446, which builds the path on which an instance outside the project sends its findings to this repository

## 1. What is needed

An identity with which the business's instance may open issues and comments in the Taktus
repository, and nothing else. The business hosts Taktus itself (DEC-0201). Its findings and its
bugs reach the product as issues here, once its operator enables it (UC-6.12, ADR-0112). To write
an issue, its instance needs an identity on the repository service. Only you, as the owner of the
repository, can create one with a right on it. The recommended identity is a second app of
yours, installed on this repository alone, with the right to read and write issues.

## 2. Why

Without it, the business's instance records its findings and shows them to its operator, who has
to send each one by hand (`taktusctl findings`). With it, the operator sets one setting and the
findings arrive on their own, with every later occurrence added to the same issue. A bug a person
of the business reports with `taktusctl findings report` is sent after they confirm it.

Taktus's own app cannot be used. Its key also writes code and pull requests in this repository,
and it must never leave the project. An account of the business would work without you, since
anyone may open an issue in a public repository. But the issues would then appear under that
account's name, possibly a person's (principle 14), and their labels would not be set.

## 3. By when

**2026-10-31**, when the business's stage 0 is meant to start (#400). Without it, the business's
findings wait on the instance, and its operator sends them by hand. Nothing else waits.

## 4. How to provide it

Recommended: a second app.

1. On the repository service, create a new app under your account. Name it for what it does, for
   example "Taktus findings". It needs no webhook.
2. Give it these permissions and no others: **Issues: read and write**, **Metadata: read**.
3. Install it on this repository only.
4. Generate a private key for it. The service gives you a file once.
5. Hand the app's identifier and the key file to the business's operator, through a channel you
   both trust, never through this repository, an issue or a chat with a session.
6. The business's operator configures the repository connector that serves its findings with
   them (`CREDENTIALS.md`, row *Findings sender identity*): the identifier as
   `TAKTUS_REPOSITORY_APP_ID`, the key as the file `TAKTUS_CREDENTIAL_REPOSITORY_APP_KEY_FILE`
   names. Its instance then names that connector's address in `TAKTUS_FINDINGS_CONNECTOR`.
7. It rotates when it may have been seen: generate a new key in the app's settings, hand it over
   the same way, and delete the old one.

The other way, without you: the business uses an account of its own that is not a person's,
with a token that may open issues. Its findings then appear under that account, without labels.

## 5. What it must never be

Never the key's content, its file's path on the business's machine, or the app's identifier in
this repository, an issue, a log or a chat with a session. The key goes from you to the
business's operator directly, and from them into a file only their connector reads.

## 6. What happens next

Once the business's operator has configured it, the scheduler of its instance sends its findings
at its next interval, on its own. Answer in the issue with the sentence "NEED-0031: provided".

## 7. How to confirm

On the repository service, the app's page lists one installation, on this repository. After the
business's instance has run with the setting, this prints the number of findings it opened:

```bash
gh issue list --repo Jersyfi/taktus --search "taktus-finding in:body" --state all --json number --jq length
```
