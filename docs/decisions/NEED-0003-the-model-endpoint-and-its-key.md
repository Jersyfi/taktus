# NEED-0003 — The model endpoint and its key

**Kind:** credential
**Raised in:** [#22](https://github.com/Jersyfi/taktus/pull/22), which adds the needs request and the status report
**Issue:** [#20](https://github.com/Jersyfi/taktus/issues/20)
**Needed by:** 2026-10-05
**Foreseeable since:** [#13](https://github.com/Jersyfi/taktus/pull/13), which built the model port and P-02's language-model step, and said in a note that the first run stopped for lack of a model credential

## 1. What is needed

A language-model endpoint that Taktus may ask, and the key it requires if it requires one. The
endpoint must answer the chat-completions dialect — the request shape most model services and
local model servers speak (`POST <endpoint>/chat/completions`) — because that is the one
dialect the model adapter uses, so that the endpoint stays interchangeable. Two settings and,
usually, one file: the endpoint's base URL, the model's name, and the key.

## 2. Why

Process P-02 Refinement has a step `refine` of method `llm` and purpose `reasoning`: it derives
the acceptance criteria of an issue from its text and its comments. It is the step at which the
first run of 2026-09-19 stopped: *no model is configured for the purpose 'reasoning'*. Without
it P-02 never writes the criteria, P-03's admission check refuses the issue (correctly), and
the coding worker is never reached. It is the first of the three needs the first live run
meets, and the only one that is not a credential alone: an endpoint without a key — a local
model server — is enough.

## 3. By when

**2026-10-05**, with NEED-0001 and NEED-0002.

If it is not there by then: P-02 cannot run to its end, the first live run does not happen, and
`0.1.0` stays incomplete (NEED-0001 §3). There is no stand-in: a faked answer at this step
would prove nothing about the bundle, and none is made.

## 4. How to provide it

**Recommended: the same Anthropic workspace as NEED-0001, through Anthropic's
chat-completions-compatible endpoint.** One workspace, one spend limit, one bill for both the
thinking step and the coding step; and the key of NEED-0001 serves here too, so that there is
one credential to rotate, not two. If you prefer a different provider or a local model server,
the settings are the same three and the key may be absent.

1. **Endpoint and model** — not secrets — in `.env` in the checkout:

   ```bash
   TAKTUS_MODEL_ENDPOINT=https://api.anthropic.com/v1
   TAKTUS_MODEL_NAME=claude-opus-5
   ```

   The adapter appends `/chat/completions` to the endpoint. Anthropic's compatibility endpoint
   accepts the API key as a bearer token, which is how the adapter sends it. The model named is
   the current default model; the name is one line to change, and the ledger records which
   model answered. (`TAKTUS_MODEL_PURPOSES` may stay unset: the default
   serves every purpose a process names.)

2. **The key**, as a file. If you provided NEED-0001 as an API key, the same file serves:

   ```bash
   TAKTUS_CREDENTIAL_MODEL_API_KEY_FILE=/Users/<you>/.config/taktus/coding-agent-api-key
   ```

   If NEED-0001 is a subscription token, create a separate API key for this purpose in the
   same workspace, exactly as NEED-0001 §4 Way A describes (a workspace with a spend limit, a
   key named "taktus model", a file `~/.config/taktus/model-api-key` with mode `600`), and name
   that file instead. A subscription token does not serve this endpoint.

3. **A local model server instead** (an endpoint on your own machine that speaks the dialect):
   set `TAKTUS_MODEL_ENDPOINT` to its URL (`http://127.0.0.1:<port>/v1`), `TAKTUS_MODEL_NAME`
   to the model it serves, and leave `TAKTUS_CREDENTIAL_MODEL_API_KEY_FILE` unset. The run then
   costs nothing per token and the quality of the criteria is that model's; `docs/runs/2026-09-19-the-run-that-stopped.md`
   records which model produced them either way.

4. **Validity and rotation:** as the key of NEED-0001. The adapter reads the file when it is
   built, at the start of a run, and keeps nothing; a rotation is a change of the file.

**Scope:** the key authenticates requests to the model endpoint and nothing else; it reaches
no repository and no system. Taktus sends the step's prompt — the issue's text and comments,
which are public — and receives text.

## 5. What it must never be

- **Never pasted into a chat, a session, an issue or a pull request**, and never typed on a
  command line. A session asks for the file's path, never its content.
- **Never committed**; `.env` names the file's path and is ignored by git. The endpoint URL and
  the model name are not secrets, and they still belong in `.env`, not in a committed file,
  because they are one deployment's choice.
- **Never in your shell's environment**: `tools/first_run.sh` reads `.env`, and the adapter
  reads the file into the request header and nowhere else; the startup log shows the setting
  masked.
- **Never named here by your Console's or your vault's name for it.**

Where it goes instead: the file of section 4, and its path in `.env`.

## 6. What happens next

With NEED-0001 and NEED-0002: `tools/first_run.sh 11`. P-02's `refine` step asks the endpoint
once, its answer is checked by the step's own check before it leaves the step (an answer that
fails the check fails the step), and P-02 writes the criteria as a comment on issue #11. The
sentence to the session: **"NEED-0003 is provided; the endpoint, the model and the file are
named in `.env`."** The session confirms with section 7 and records the outcome here.

## 7. How to confirm

Without revealing the value — one request of a few tokens on the exact path the adapter uses;
prints an HTTP status, where `200` means the endpoint accepts the key and serves the model (a
local server without a key: the same command without the `Authorization` header):

```bash
curl -sS -o /dev/null -w '%{http_code}\n' \
  "$(sed -n 's/^TAKTUS_MODEL_ENDPOINT=//p' .env)/chat/completions" \
  -H "Authorization: Bearer $(cat "$(sed -n 's/^TAKTUS_CREDENTIAL_MODEL_API_KEY_FILE=//p' .env)")" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$(sed -n 's/^TAKTUS_MODEL_NAME=//p' .env)\",\"max_tokens\":5,\"messages\":[{\"role\":\"user\",\"content\":\"ok\"}]}"
```

`tools/first_run.sh` checks that the endpoint and the model name are set before it starts
anything. The first real confirmation is P-02's own: its `refine` step ends `succeeded` and the
ledger of that run shows the tokens it consumed.

## Outcome

**Provided:** 2026-09-22
**Confirmed by:** section 7, run on 2026-09-23 in the checkout of
[#23](https://github.com/Jersyfi/taktus/pull/23). One request of a few tokens on the exact path
the adapter uses — the endpoint named by `TAKTUS_MODEL_ENDPOINT` plus `/chat/completions`, the
model named by `TAKTUS_MODEL_NAME`, the key from the file named by
`TAKTUS_CREDENTIAL_MODEL_API_KEY_FILE` — answered `200`. The check printed a status and nothing
else.
**What was provided:** the recommended shape of section 4. The endpoint is the provider's
chat-completions-compatible one; the key is the file of NEED-0001, so there is one credential
to rotate and its renewal is NEED-0005, not a second one. `TAKTUS_MODEL_PURPOSES` stays unset:
the one configured model serves every purpose a process names, and `reasoning` is the only one
any bundle names today.
**Which model:** the owner chose the smaller model of the family rather than the current
default that section 4 gave as an example — the cheapest model that does the job, method
selection applied to the model within the method. The choice, its reasons and what would
revisit it are DEC-0019. The model's name is in this deployment's `.env` and in no file of
this repository.
**What it unlocked:** P-02's step `refine`, which is where the run of 2026-09-19 stopped, and
with it the first live run (`docs/runs/first-run.md`).
**Recorded in:** [#23](https://github.com/Jersyfi/taktus/pull/23)
