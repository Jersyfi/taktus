# NEED-0018 — An app in the owner's chat workspace

**Kind:** account
**Raised in:** [#148](https://github.com/Jersyfi/taktus/pull/148)
**Issue:** [#146](https://github.com/Jersyfi/taktus/issues/146)
**Needed by:** 2026-10-31
**Foreseeable since:** [#148](https://github.com/Jersyfi/taktus/pull/148), where the chat connector was built (issue #84)

## 1. What is needed

Taktus's own app in your chat workspace, and two of its secrets. The chat connector — the
adapter through which Taktus posts into a conversation and receives what a person writes there —
exists and passes its conformance suite against a stand-in for the chat service. To run the same
suite against the real service, and later to talk with you there, it needs an app in your
workspace that acts as Taktus: an identity of its own, not you. Concretely:

1. **The app**, created from the manifest below, installed in your workspace. It may post
   messages, read the conversations it is in, and receive a mention — nothing else.
2. **A scratch conversation** for the monthly live test: a private channel that exists for the
   test alone, with the app in it.
3. **Its bot token** in the environment `live` of this repository, and the channel's identifier
   beside it.
4. **Its bot token and its signing secret** in two files on your workstation, for the instance
   that will run the owner-facing channel (#85).

## 2. Why

Issue #84 built the chat connector: the capability `chat.threads` and the channel
`channel.chat`. Against a fake of the service it passes every check, but only the real service
can show that its interface keeps what the connector relies on: a message's metadata, which is
where the connector writes the key that recognises a repeat, and a thread read in order. The
workflow `live` has a job `chat` that runs the suite there, monthly and by dispatch on `main`
(DEC-0048). Until this need is provided the job says "nothing ran".

The owner-facing channel (#85, UC-6.11) rests on this connector: decisions and needs reach you in
the chat, and your answers come back through it. It cannot reach you without the app. The
signing secret is what every event the service sends is verified with; without it no message
you write reaches Taktus.

## 3. By when

**2026-10-31**, before the workflow's next monthly run on 2026-11-01.

If it is not there by then: that run says "nothing ran", and the connector's interface to the
real service stays proven against a stand-in only. The owner-facing channel (#85) can be built
against the stand-in, but cannot be shown to you. A half-done step 4 — the variable without the
token — makes the run fail, on purpose: half a configuration is a fault, not a skip.

## 4. How to provide it

**Step 1 — create the app from a manifest.** At the service's app directory for developers
(`https://api.slack.com/apps`), choose *Create New App → From a manifest*, pick your workspace,
and paste this manifest. It names every permission the connector needs and no other.

```yaml
display_information:
  name: Taktus
features:
  bot_user:
    display_name: Taktus
    always_online: false
  app_home:
    messages_tab_enabled: true
    messages_tab_read_only_enabled: false
oauth_config:
  scopes:
    bot:
      - chat:write          # post a message (chat.threads.post)
      - groups:history      # read a thread in a private channel, and find its own mark there
      - im:history          # the same in a direct message with you
      - app_mentions:read   # receive a mention
settings:
  org_deploy_enabled: false
  socket_mode_enabled: false
  token_rotation_enabled: false
```

There is no event subscription yet. Its request URL can be set only once the instance answers the
service's URL check (issue #145); that is a later step under #85, not this need. If you ever
talk to Taktus in a public channel, `channels:history` is added then, not now.

**Step 2 — install it.** On the app's page, *Install App → Install to Workspace*, and allow.
The page then shows the **Bot User OAuth Token**, starting `xoxb-`. *Basic Information → App
Credentials* shows the **Signing Secret**. Neither is copied anywhere but in steps 4 and 5.

**Step 3 — the scratch conversation.** Create a private channel for the live test alone, with a
name of your choosing. In it, type `/invite @Taktus`. Open the channel's details: its
**Channel ID**, starting `C`, is at the bottom. The test posts a handful of messages there each
month and deletes none.

**Step 4 — the environment `live`.** In the repository's *Settings → Environments → live*, or
from your workstation; the token is typed at the prompt, never written on a command line.

| Kind | Name | Value |
|---|---|---|
| secret | `LIVE_CHAT_TOKEN` | the Bot User OAuth Token of step 2 |
| variable | `TAKTUS_LIVE_CHAT_CONVERSATION` | the Channel ID of step 3 |

```sh
gh secret set LIVE_CHAT_TOKEN --env live --repo Jersyfi/taktus              # prompts for it
gh variable set TAKTUS_LIVE_CHAT_CONVERSATION --env live --repo Jersyfi/taktus --body "<the channel id>"
```

**Step 5 — the two files.** On your workstation, each secret into a file readable by you alone,
outside the checkout — the same place as the other credential files. In an editor, or with:

```sh
umask 077
read -rs token && printf '%s' "$token" > "<the token's file>"; unset token
read -rs secret && printf '%s' "$secret" > "<the signing secret's file>"; unset secret
```

and in the checkout's `.env`:

```
TAKTUS_CREDENTIAL_CHAT_TOKEN_FILE=<the token's file>
TAKTUS_CREDENTIAL_CHAT_SIGNING_SECRET_FILE=<the signing secret's file>
```

On the platform they go into the instance's secret when the chat connector is deployed with the
owner-facing channel (#85); the chart then mounts them as files under the same two variables.

**Validity and rotation.** With token rotation off, the bot token does not expire. Both are
replaced when they may have been seen: the token by reinstalling the app (*Install App →
Reinstall*), the signing secret by *Regenerate* under *App Credentials*. A new value goes into
the same file and the same environment secret in one move.

## 5. What it must never be

- **Never pasted** into a chat — this chat workspace included —, a session, an issue, a pull
  request or a command line, and never committed. The token goes from the app's page into the
  environment's secret and into its file, and nowhere else.
- **Never a repository secret**, and never in another environment: only the workflow `live`, on
  `main`, may read it (DEC-0048).
- **Never your own user token** (`xoxp-`): Taktus acts as its app, not as you.
- **Never more scopes than the manifest names.** A scope added "just in case" lets Taktus see
  what no process needs.
- **No workspace name, channel name or identifier in this repository.** The channel's ID lives
  in the environment's variable; the files' paths in your `.env`.

## 6. What happens next

Write in the issue: **"NEED-0018 is provided."** The next session records it first, dispatches
the workflow `live` once on `main` (`gh workflow run live.yml --ref main`), and records the
outcome. Afterwards the job `chat` runs on its own, on the first of every month.

## 7. How to confirm

Without revealing anything:

```sh
gh secret list --env live --repo Jersyfi/taktus      # lists LIVE_CHAT_TOKEN
gh variable list --env live --repo Jersyfi/taktus    # lists TAKTUS_LIVE_CHAT_CONVERSATION
test -s "<the token's file>" && test -s "<the signing secret's file>" && echo "both files hold a value"
```

The dispatched run of the job `chat` is green, and its log carries `PASSED` for
`test_the_suite_passes_against_the_real_service` and for
`test_a_reply_retried_after_a_restart_is_posted_once_on_the_real_service`. The scratch channel
shows a message from Taktus that begins *Conformance run*, with its replies in one thread, and
exactly one answer in the thread of the message that begins *Restart test*.
