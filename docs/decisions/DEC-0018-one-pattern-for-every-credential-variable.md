# DEC-0018 — One pattern for every credential variable

**Category:** DEFECT
**Raised in:** [#23](https://github.com/Jersyfi/taktus/pull/23), which wires the three credentials and raises their renewals
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

The repository states one rule for how a secret reaches the software. CLAUDE.md §9: "A secret
value is read from a file the variable points at (`TAKTUS_<KEY>_FILE`)". `CREDENTIALS.md` says
the same for a credential, whose configuration key is `credential.<name>`, so that the variable
is `TAKTUS_CREDENTIAL_<NAME>_FILE`. `.env.example` repeats it. The environment configuration
adapter derives exactly that name from the key
(`src/taktus/adapters/driven/configuration/environment.py`).

Three variables did not follow the rule. `tools/first_run.sh` read the repository token from
`REPOSITORY_TOKEN_FILE` and the coding agent's credential from `CODING_AGENT_API_KEY_FILE` or
`CODING_AGENT_SESSION_FILE`, with no prefix, while the model's key in the same script came from
`TAKTUS_CREDENTIAL_MODEL_API_KEY_FILE`, with one. The steps the owner was given followed the
script: NEED-0001 and NEED-0002 told him to write the unprefixed names into `.env`, NEED-0003
the prefixed one.

Worse than the ragged look: **one credential had two names.** The coding agent's API key was
`TAKTUS_CREDENTIAL_CODING_AGENT_API_KEY_FILE` when the execution adapter started the unit in a
container and `CODING_AGENT_API_KEY_FILE` when `tools/first_run.sh` started the same worker by
endpoint — the same file, the same credential, two lines in `.env`, and nothing saying they
were the same thing. An owner who moved from the endpoint worker to a container would have had
to discover the second name from a table.

## 2. Why you are being asked

You are not. The code contradicted a rule the documentation states in three places. CLAUDE.md
§1 says that where code and a stated rule disagree, the code is the finding. Entry M1.4 of
`docs/decisions/anchors.taktus.md` makes the correction the session's, recorded here. The
correction also changes what an operator must write in `.env`, which is a behaviour change
inside an agreed scope, entry M2.4 — that half is recorded as the notice NTC-0003.

## 3. What you must decide

Nothing. The correction is made; the record exists so that the precedent is findable and so
that the next credential is named without asking.

## 4. What you need to know to decide

- The rule, now stated once in `CREDENTIALS.md` under the parameter table's introduction: a
  credential's configuration key is `credential.<name>`; the file that holds its value is named
  by `TAKTUS_CREDENTIAL_<NAME>_FILE`; the variable is the same whoever reads it — the
  composition root, the execution adapter, a worker started by endpoint, `tools/first_run.sh`.
- The three variables are new to the owner as of this pull request: nothing was in `.env`
  before it, because the credentials did not exist before it. Nobody has to edit an existing
  file, and no deployment carries the old names.
- The coverage gate (`make gate-decisions`, ADR-0028 §2) already fails a `<NAME>_FILE` variable
  the code reads that `CREDENTIALS.md` does not describe. It does not check the *shape* of the
  name, which is why it passed three names that broke the pattern; that gap is stated in §5.

## 5. Options

None for the owner. What the session did: renamed the three variables in `tools/first_run.sh`,
`.env.example`, `CREDENTIALS.md` and the steps of NEED-0001 and NEED-0002; stated the pattern
once in `CREDENTIALS.md` instead of implying it from four rows; and left the coverage gate as
it is. The gate is not extended to enforce the shape here, because a needs request may
legitimately name a variable that is not a credential, and a gate written from one example
tends to be the next defect. The gap is named instead, in this record and in
`docs/status.md` §5: the register's rule is enforced by reading, not by a check.

## 6. What is blocked

Nothing. The first live run uses the corrected names.

## 7. How to answer

Nothing to answer. To object to the correction: "Reopen DEC-0018" in an issue, with the reading
you hold.

## Outcome

**Corrected:** 2026-09-23
**What was wrong:** `tools/first_run.sh` read `REPOSITORY_TOKEN_FILE`,
`CODING_AGENT_API_KEY_FILE` and `CODING_AGENT_SESSION_FILE`, and `.env.example`, `CREDENTIALS.md`,
NEED-0001 and NEED-0002 named them the same way, while CLAUDE.md §9 and `CREDENTIALS.md` state
that a secret's file is named `TAKTUS_<KEY>_FILE` and a credential's `TAKTUS_CREDENTIAL_<NAME>_FILE`.
The coding agent's key had two names for one file, depending on whether the worker was started
by the execution adapter or by the script.
**Why it was wrong:** a rule that holds for three variables out of six is not a rule, and an
owner following the steps writes whichever name the page in front of him happens to carry. One
credential with two names is worse than an ugly name: it is a second thing to keep in step.
**What it now says:** every credential's file is named `TAKTUS_CREDENTIAL_<NAME>_FILE`, the
same variable whoever reads it; the pattern is stated once in `CREDENTIALS.md` and the four
rows point at it. `tools/first_run.sh` reads `TAKTUS_CREDENTIAL_REPOSITORY_TOKEN_FILE`,
`TAKTUS_CREDENTIAL_CODING_AGENT_API_KEY_FILE` and `TAKTUS_CREDENTIAL_CODING_AGENT_SESSION_FILE`.
**What changed in substance:** the three variable names the script reads, and the three lines
of `.env` an operator writes. Nothing else: the same files hold the same values and reach the
same processes. Recorded as a behaviour change in NTC-0003.
**Recorded in:** [#23](https://github.com/Jersyfi/taktus/pull/23)
