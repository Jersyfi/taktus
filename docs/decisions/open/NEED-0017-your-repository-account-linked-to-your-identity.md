# NEED-0017 — Your repository account linked to your identity

**Kind:** action
**Raised in:** [#149](https://github.com/Jersyfi/taktus/pull/149), for issue #82
**Issue:** [#147](https://github.com/Jersyfi/taktus/issues/147)
**Needed by:** 2026-10-31
**Owner's direction:** 2026-10-10: accounts should be linked with little effort for users and administrators — for example, Taktus reads a platform's users and an administrator links them to a Taktus identity, so that Taktus knows each person's accounts across platforms; automatic, manual and handle-only links are all to be considered, and proven technically. The session works out a proposal before this need is provided.
**Foreseeable since:** [#149](https://github.com/Jersyfi/taktus/pull/149), where the identity component replaced the provisional operator identity (ADR-0040)

## 1. What is needed

On the installed Taktus instance, your account on the repository service must be linked to your
Taktus identity. Only you can make that link: it is made by writing a code, from your account,
in an issue of this repository. Three short acts, each with something that already exists or
that the instance prints for you.

## 2. Why

Until now every event the instance received was treated as yours, whoever caused it: one
configured operator identity stood in for everybody (DEC-0013). That is gone. The instance now
acts on an event only when the sender's account is linked to an identity, and a link is made only
by the person who holds the account (UC-1.7). Until your account is linked, a comment you write
on an issue is answered with an offer to link, and nothing is done with it. Event reactions
(#77), where an issue you comment on starts P-02 or P-03, need the link.

## 3. By when

**2026-10-31**, before event reactions (#77) are installed on the instance.

If it is not there by then: the instance answers your comments with the offer to link and acts
on none of them. Runs started from the command line are not affected.

## 4. How to provide it

**Step 1 — your identity on the instance.** Whoever administers the instance — you, or a
session on your word — runs once, inside one of the instance's control plane containers, whose
image carries `taktusctl` and the database's configuration:

```sh
taktusctl identity add idn_owner
```

It prints an **account key**, once. It goes straight into your password manager, nowhere else.

**Step 2 — a link code from your account.** From your workstation, with the key read from your
password manager into the variable, never typed on the command line:

```sh
read -rs TAKTUS_KEY    # paste the key; nothing is shown
curl -fsS -X POST "https://<the instance's public name>/identity/link-codes" \
  -H "Authorization: Bearer $TAKTUS_KEY" -H "Content-Type: application/json" \
  -d '{"channel": "channel.repo"}'
unset TAKTUS_KEY
```

The answer carries a `code` that starts with `tkl-`, valid for 30 minutes and only once.

**Step 3 — the code from your account.** Write the code as a comment on any issue of this
repository, signed in as yourself. The instance answers in the same issue that the account is
now linked.

## 5. What it must never be

- **The account key never pasted** into a chat, a session, an issue, a pull request or a command
  line, and never committed. It goes from the instance's output into your password manager.
- **The code is not a secret once used**, and it is used by your comment. Do not post a code
  you did not create, and do not write yours from another account: whoever writes it first links
  their account to your identity.
- **Never a second identity for you.** One account maps to one identity; a new key, if one is
  lost, is `taktusctl identity key idn_owner`, never a new identity.

## 6. What happens next

Write in the issue: **"NEED-0017 is provided."** The next session records it first and confirms
it as section 7 says.

## 7. How to confirm

Inside the instance, without revealing anything:

```sh
taktusctl identity links
```

lists one link of origin `confirmed`, on `channel.repo`, to `idn_owner`, active. The instance's
ledger holds an `identity.linked` entry with outcome `confirmed` and actor `idn_owner`.
