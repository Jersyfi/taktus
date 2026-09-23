# NEED-0005 — Renew the coding agent's key

**Kind:** credential
**Raised in:** [#23](https://github.com/Jersyfi/taktus/pull/23), which wires the three credentials and raises their renewals
**Issue:** [#24](https://github.com/Jersyfi/taktus/issues/24)
**Needed by:** 2026-10-15
**Foreseeable since:** [#23](https://github.com/Jersyfi/taktus/pull/23), the pull request that wired the key and read its validity; raised the same day

## 1. What is needed

A new API key for the coding agent, in the same workspace and with the same purpose as the one
provided under NEED-0001, written into the same file — and the old key deleted afterwards. The
key provided on 2026-09-22 carries a validity of 30 days. It stops working on **2026-10-22**.
This request asks for the replacement one week before that, so that no run meets the expiry.

The key also serves the model endpoint: NEED-0003 points
`TAKTUS_CREDENTIAL_MODEL_API_KEY_FILE` at the same file. One key, one file, one renewal — this
one. There is no second renewal for the model.

## 2. Why

Two steps of the dev-orchestration blueprint stop without it. P-03's step `implement` hands the
issue to the coding worker, which authenticates the agent with this key; P-02's step `refine`
asks the model endpoint with it. With the key expired, `tools/first_run.sh` still starts — the
file is present, and presence is all a file check can see — and the first outward request is
refused by the provider.

The renewal is raised now rather than on 2026-10-22 because that is the timing rule of
ADR-0028: a need is raised when it becomes **foreseeable**, not when it blocks. The expiry
date was known the moment the key was wired, which is why this request has the same date as
the pull request that wired it.

## 3. By when

**2026-10-15**, one week before the expiry on 2026-10-22. The week is deliberate: it is long
enough that a run started on the last day finishes, and short enough that the new key is not
sitting unused for a month.

If it is not there by then: nothing breaks quietly. **What Taktus does when a credential
expires anyway** is stated once here and holds for every credential of this repository:

- **It halts at a step boundary, with the cause.** The step that used the credential ends
  `failed` with the provider's refusal as its reason, and the run escalates at that boundary.
  Every step before it stays completed with its provenance; nothing is half done.
- **It never aborts.** The run is not discarded. It stays resumable: a new key in the same
  file, and `taktusctl resume` continues at the step that failed. The escalation's last line
  says how.
- **It never retries silently.** A repository call refused as `unauthenticated` is recorded
  with effect `none` and retryable `false` — the connector contract requires exactly that, and
  the conformance suite checks it (C-03, `src/taktus/conformance/connector/rules.py`). A model
  call that is refused fails the step and stops the run; the retry is a person's act, not a
  loop. Nothing outward is repeated in the hope that it works the second time.

So the cost of a missed renewal is a halted run and the minutes it takes to notice, not a
wrong result and not a partial write. That is the design; it is not a reason to be late.

## 4. How to provide it

The same steps as NEED-0001 §4 Way A, with a deletion at the end. Ten minutes.

1. In the Anthropic Console (`console.anthropic.com`), open the workspace you created for
   Taktus. Create a new **API key** in it, named so that you can tell it from the old one —
   "taktus coding worker, from 2026-10" is enough. The Console shows the value once.
2. Write the value into the file that is already in use, replacing its content. It is the file
   `~/.config/taktus/coding-agent-api-key`, named in `.env` by
   `TAKTUS_CREDENTIAL_CODING_AGENT_API_KEY_FILE` and by
   `TAKTUS_CREDENTIAL_MODEL_API_KEY_FILE`. Use an editor, not a command line, which the shell
   history keeps. Then:

   ```bash
   chmod 600 ~/.config/taktus/coding-agent-api-key
   ```

   Nothing in `.env` changes: the path is the same, and both variables keep pointing at it.
   Nothing in Taktus stores the value, so a rotation is a change of this file and nothing else.
3. Confirm with section 7 before deleting anything.
4. **Delete the old key** in the Console, once section 7 answers `200`. A key that is no longer
   used and not deleted is a credential nobody is watching.
5. **Note the new expiry.** If the new key again carries a validity, the next renewal is due
   one week before it; say so when you close the issue, and the next session raises it as its
   own needs request with the date. A key without an expiry needs no successor request, and
   this one is then closed for good.

**Scope:** unchanged. The key authenticates the agent and the model endpoint and nothing else;
it reaches no repository and no system.

## 5. What it must never be

- **Never pasted into a chat or a session** — not into Claude Code, not into an issue, not into
  a message. A session that receives a value cannot un-receive it, and this repository is
  public. If a session asks for the value, the session is wrong.
- **Never committed**, in any file. `.env` is ignored by git and stays ignored.
- **Never on a command line** and never in your shell's environment: only
  `tools/first_run.sh` reads the file, and only into the process that needs it.
- **Never a second file.** Replacing the content of the file in use is the whole rotation; a
  new file beside the old one means two credentials, one of them forgotten.
- **Never named here by the name it has in your Console.** The repository knows the parameter
  (`CODING_AGENT_API_KEY`, `CREDENTIALS.md`), never your name for it.

Where it goes instead: the file this request names, readable by you alone, whose path is
already in `.env`.

## 6. What happens next

Nothing has to be told to anybody: the path in `.env` is unchanged, so the next run uses the
new key without a line being edited. Close issue [#24](https://github.com/Jersyfi/taktus/issues/24)
with the sentence **"NEED-0005 is provided; the file holds a new key and the old one is
deleted"**, and add the new expiry date if the key has one. The next session confirms with
section 7, records the outcome in this record, and raises the following renewal if there is
a date for it.

## 7. How to confirm

Without revealing the value — the file is present, and the key it holds is accepted. `200`
means it is:

```bash
test -s "$(sed -n 's/^TAKTUS_CREDENTIAL_CODING_AGENT_API_KEY_FILE=//p' .env)" && echo "api-key file: present"
```

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://api.anthropic.com/v1/models \
  -H "x-api-key: $(cat "$(sed -n 's/^TAKTUS_CREDENTIAL_CODING_AGENT_API_KEY_FILE=//p' .env)")" \
  -H "anthropic-version: 2023-06-01"
```

And that the same key still serves the model endpoint, which is the second thing this file is
used for:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' \
  "$(sed -n 's/^TAKTUS_MODEL_ENDPOINT=//p' .env)/chat/completions" \
  -H "Authorization: Bearer $(cat "$(sed -n 's/^TAKTUS_CREDENTIAL_MODEL_API_KEY_FILE=//p' .env)")" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$(sed -n 's/^TAKTUS_MODEL_NAME=//p' .env)\",\"max_tokens\":5,\"messages\":[{\"role\":\"user\",\"content\":\"ok\"}]}"
```

Two `200`s, and the old key gone from the Console, is the whole confirmation.
