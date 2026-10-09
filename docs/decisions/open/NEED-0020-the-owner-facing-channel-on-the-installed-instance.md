# NEED-0020 — The owner-facing channel on the instance

**Kind:** action
**Raised in:** [#PRNUMBER](https://github.com/Jersyfi/taktus/pull/PRNUMBER), for issue #85
**Issue:** [#ISSUENUMBER](https://github.com/Jersyfi/taktus/issues/ISSUENUMBER)
**Needed by:** 2026-11-07
**Foreseeable since:** [#PRNUMBER](https://github.com/Jersyfi/taktus/pull/PRNUMBER), where the owner-facing channel was built

## 1. What is needed

On the installed Taktus instance, your chat account linked to your Taktus identity, that
identity holding the role `owner`, and the instance told where to reach you: the identifier of
your direct conversation with Taktus's app. Three short acts on top of two needs that come first:
Taktus's app in your chat workspace (NEED-0018) and your identity on the instance (NEED-0017).

## 2. Why

The owner-facing channel exists (issue #85): a decision request addressed to you, a need, a date
or a failure Taktus noticed about itself reaches you as a message in German, and you answer in
its thread. On the instance it cannot reach you until it knows your conversation, and it files
no answer of yours until your chat account is linked to your identity: an answer from an account
nobody linked is told that it is not filed. A decision request addressed to the role `owner`
reaches you only once your identity holds that role.

## 3. By when

**2026-11-07**, a week after NEED-0018's date, so that the app and its secrets are in place.

If it is not there by then: every report stays on the control plane's surface (`GET
/owner/reports`), where you have to look for it, and a decision request addressed to you waits
there as it does today. Nothing is lost; nothing reaches you either.

## 4. How to provide it

**Before:** NEED-0018 steps 1 to 6 (the app, installed, its two secrets on the instance, its events sent to the instance) and
NEED-0017 step 1 (your identity `idn_owner` on the instance, with its account key in your
password manager).

**Step 1 — the role.** Whoever administers the instance — you, or a session on your word — runs
once, inside one of the instance's control plane containers:

```sh
taktusctl identity roles idn_owner --role owner
```

**Step 2 — your chat account linked.** From your workstation, with the key read from your
password manager into the variable, never typed on the command line:

```sh
read -rs TAKTUS_KEY    # paste the key; nothing is shown
curl -fsS -X POST "https://<the instance's public name>/identity/link-codes" \
  -H "Authorization: Bearer $TAKTUS_KEY" -H "Content-Type: application/json" \
  -d '{"channel": "channel.chat"}'
unset TAKTUS_KEY
```

The answer carries a `code` starting with `tkl-`, valid for 30 minutes and once. Open the direct
conversation with Taktus's app in your chat workspace (*Apps → Taktus → Messages*) and write the
code there as a message. Taktus answers in that conversation that your account is linked.

**Step 3 — where to reach you.** In the same direct conversation, open its details: its
identifier starts with `D`. Write a file `owner-channel.json` on the instance, with that
identifier in place of the placeholder, and configure it:

```json
{
  "owner": "idn_owner",
  "channel": "channel.chat",
  "address": "<the conversation's identifier, starting with D>",
  "language": "de",
  "view_base": "https://<the instance's public name><the instance's path prefix>"
}
```

```sh
taktusctl owner-channel set owner-channel.json --identity idn_owner
```

It answers `owner-facing channel of default configured: channel.chat, in de, 0 named`. To let
someone answer in your place, add their identity under `"named"` and run the command again.

## 5. What it must never be

- **The account key never pasted** into a chat, a session, an issue, a pull request or a command
  line, and never committed. It goes from your password manager into the variable and nowhere
  else.
- **The code written only by you, from your own chat account.** Whoever writes a valid code first
  links their account to your identity.
- **The conversation's identifier and the instance's name never in this repository.** They live
  in the file on the instance and in your private note.
- **Never a channel shared with others as the address**, unless everyone in it may read what
  Taktus needs from you: the messages name decisions, needs and failures.

## 6. What happens next

Write in the issue: **"NEED-0020 is provided."** The next session records it first and confirms
it as section 7 says. From then on, every report reaches you in that conversation, and every
answer you confirm there is filed.

## 7. How to confirm

Inside the instance, without revealing anything:

```sh
taktusctl identity links            # one active link on channel.chat to idn_owner
taktusctl owner-channel show        # owner idn_owner, channel channel.chat, language de
```

The instance's ledger holds an `identity.linked` entry for `channel.chat` with actor `idn_owner`,
an `identity.roles_set` entry for `idn_owner`, and an `owner_channel.configured` entry.
