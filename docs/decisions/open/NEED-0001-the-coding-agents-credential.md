# NEED-0001 — The coding agent's credential

**Kind:** credential
**Raised in:** [#22](https://github.com/Jersyfi/taktus/pull/22), which adds the needs request and the status report
**Issue:** [#18](https://github.com/Jersyfi/taktus/issues/18)
**Needed by:** 2026-10-05
**Foreseeable since:** [#10](https://github.com/Jersyfi/taktus/pull/10), which built the coding worker and said in a note that a live run needs this

## 1. What is needed

A credential with which the coding worker — the part of Taktus that writes code — can use its
coding agent, Claude Code, for real. Two kinds work, and you provide one of them: an **API
key** from the Anthropic Console, billed per token to your Anthropic account; or a
**subscription token**, issued by the agent's own `claude setup-token` command from a Claude
subscription (Pro or Max) that you hold. The worker takes either; which one decides how usage
is counted (section 4 says which is recommended and why).

## 2. Why

It unlocks the completion criterion of milestone `0.1.0`: *Taktus turns one of its own issues
into a pull request that passes CI.* Process P-03 Implementation of the dev-orchestration
blueprint has a step `implement` that hands the issue and its acceptance criteria to the coding
worker; the worker starts the agent, and the agent needs to authenticate. Without the
credential the worker rejects the assignment before the agent starts, and the step never runs.
The first run of 2026-09-19 (`docs/first-run.md`) stopped for exactly this reason. The command
that finishes it, `tools/first_run.sh 11`, checks for the credential's file before it does
anything and stops with a sentence naming it when the file is absent.

Everything after `0.1.0` is built on a run that has never completed: the budget of `0.2.0` is
spent against a coding step that has never been measured for real, and the deployment of the
next pull request but one packages a worker that has never run live.

## 3. By when

**2026-10-05.** Two weeks from the day this is raised, so that the first live run is the next
pull request after this one, as the status file says it should be.

If it is not there by then: `0.1.0` stays incomplete, the first live run does not happen, and
the next sessions build the deployment and the `0.2.0` budget on assumptions about the coding
step — its duration, its tokens, its money — instead of on one measured run. Nothing breaks;
nothing is proven either, and every week without it is a week in which the roadmap's ordering
rule ("nothing from a later version is built while the previous one is not complete") is either
broken or idle.

## 4. How to provide it

Both ways are described. **The API key is recommended for this project**, because: the worker
reports tokens per step and money at the end, and admission control converts a currency budget
into tokens (ADR-0005) — which needs a price per token, and only an API key has one; a key does
not expire in the middle of a run, while a subscription's usage window can run out and halt the
assignment at its last boundary until the window opens again; a key lives in a workspace of
its own with a spend limit, separate from anything you use interactively; and revoking a key
touches nothing else you use. A subscription costs a fixed amount and is the right choice when
the runs are few and the fixed cost is already paid; its usage is shared with your own
interactive use of the same subscription, and the worker counts *turns* as a stand-in because
the agent does not expose what the window counts.

Whichever you choose, the credential is a **file** on the machine that runs Taktus, readable by
you alone, and the file's **path** — never its content — goes into `.env` in the checkout,
which git ignores.

### Way A — an API key (recommended)

1. In the Anthropic Console (`console.anthropic.com`), create a **workspace** for Taktus —
   "taktus" — so that its spend, its keys and its limits are separate from any other use.
   Set a **monthly spend limit** on the workspace; the first runs need a few dollars, not
   more.
2. In that workspace, create an **API key** named for what it is for — "taktus coding worker".
   The Console shows the value once.
3. Put the value into a file, and nowhere else. On the machine that will run Taktus:

   ```bash
   mkdir -p ~/.config/taktus && chmod 700 ~/.config/taktus
   ```

   Then create `~/.config/taktus/coding-agent-api-key` with the value as its only content
   (an editor is fine; do not type it on a command line, which the shell history keeps), and:

   ```bash
   chmod 600 ~/.config/taktus/coding-agent-api-key
   ```

4. Point Taktus at the file, in `.env` in the checkout (copy `.env.example` to `.env` if it
   does not exist yet; git ignores `.env`):

   ```bash
   TAKTUS_CREDENTIAL_CODING_AGENT_API_KEY_FILE=/Users/<you>/.config/taktus/coding-agent-api-key
   ```

   That is the same line whichever way the worker runs: by endpoint, as the first run starts
   it, or in a container the control plane starts (`TAKTUS_EXECUTION=container`). One
   credential has one variable (`CREDENTIALS.md`, DEC-0018).

5. **Validity:** a key does not expire. **Rotation:** whenever it may have been seen, and at
   the latest when the identity component of `0.2.0` replaces the provisional identity —
   create a new key in the Console, write it into the file, delete the old key in the Console.
   Nothing in Taktus stores the value, so a rotation is a change of the file.

### Way B — a subscription token

1. On a machine where Claude Code is installed and logged in with the subscription, run:

   ```bash
   claude setup-token
   ```

   It opens the browser for consent and prints a long-lived token once.
2. Put the printed value into `~/.config/taktus/coding-agent-session` exactly as in step 3 of
   Way A (directory `700`, file `600`, no command line).
3. In `.env`:

   ```bash
   TAKTUS_CREDENTIAL_CODING_AGENT_SESSION_FILE=/Users/<you>/.config/taktus/coding-agent-session
   ```

   Only one of the two lines is set; the one that is set decides the worker's authentication
   mode.
4. **Validity:** the token is long-lived but not permanent — the agent's documentation states
   the current lifetime; note the date. A token that expires mid-run halts the assignment at
   its last boundary with the cause; a new token in the same file resumes it. **Rotation:**
   run `claude setup-token` again and replace the file's content.

**Scope in both ways:** the credential authenticates the agent and nothing else. It reaches no
repository and no system; the worker hands it to the agent under the agent's own variable and
gives the agent nothing else from its environment.

## 5. What it must never be

- **Never pasted into a chat or a session** — not into Claude Code, not into a Taktus issue,
  not into a message. A session that receives a value cannot un-receive it, and this repository
  is public. If a session asks for the value, the session is wrong.
- **Never committed** to this or any repository, in any file, including `.env`, which is ignored
  by git and stays that way.
- **Never on a command line** (`CODING_AGENT_API_KEY=... tools/first_run.sh`), which the shell
  history and the process list keep.
- **Never in an environment variable set for your whole shell** — only `tools/first_run.sh`
  reads the file and puts the value into the worker's process environment for the length of
  the run.
- **Never named here by the name it has in your Console or your vault** — the repository knows
  the parameter (`CODING_AGENT_API_KEY` or `CODING_AGENT_SESSION`, `CREDENTIALS.md`) and never
  your name for it.

Where it goes instead: the file of section 4, readable by you alone, and its path in `.env`.

## 6. What happens next

Once the file exists and `.env` names it, together with NEED-0002 (the repository token) and
NEED-0003 (the model endpoint), the first live run is one command, which you run yourself or
tell the next session to run:

```bash
tools/first_run.sh 11
```

The sentence to the session: **"NEED-0001 is provided; the file is named in `.env`."** The
session confirms with section 7, never by reading the file, and records the outcome in this
record, which then moves from `docs/decisions/open/` into the register. The issue is closed
with the same sentence.

## 7. How to confirm

Without revealing the value:

```bash
test -s "$(sed -n 's/^TAKTUS_CREDENTIAL_CODING_AGENT_API_KEY_FILE=//p' .env)" && echo "api-key file: present"
```

or, for a subscription token, the same with `TAKTUS_CREDENTIAL_CODING_AGENT_SESSION_FILE`. Then that the
credential works, which prints an HTTP status and nothing else — `200` means it does:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://api.anthropic.com/v1/models \
  -H "x-api-key: $(cat "$(sed -n 's/^TAKTUS_CREDENTIAL_CODING_AGENT_API_KEY_FILE=//p' .env)")" \
  -H "anthropic-version: 2023-06-01"
```

For a subscription token, the agent itself is the check — it answers `ok` when the token
works and an authentication error when it does not:

```bash
CLAUDE_CODE_OAUTH_TOKEN="$(cat "$(sed -n 's/^TAKTUS_CREDENTIAL_CODING_AGENT_SESSION_FILE=//p' .env)")" \
  claude -p "reply with the word ok" --max-turns 1
```

`tools/first_run.sh` performs the file check itself before it starts anything and names the
variable that is missing.
