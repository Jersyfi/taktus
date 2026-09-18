# The first run

The record of the first time Taktus was *used* against this repository rather than tested:
issue [#11](https://github.com/Jersyfi/taktus/issues/11) through P-02 Refinement and P-03
Implementation of the dev-orchestration blueprint, on 2026-09-19, from the session that built
the action half of the connector (pull request #13). Every piece of friction below is a
product finding, not a complaint.

**How far it got, in one sentence:** the reads and the checks ran against the real repository
through the reference connector; the language-model step and the coding-worker step did not
run, because the session had no credential for a model endpoint and none for the coding agent,
and a simulated run would have proven nothing. `tools/first_run.sh 11` runs the whole thing in
one command once those two credentials exist.

## What ran, and what did not

| Stage | State | Evidence |
|---|---|---|
| A genuine issue | done | #11, "make doctor does not report git, which gate-docs and the coding worker need" — a real, small gap: `tools/preflight.sh` does not know `git`, which `make gate-docs` and the coding worker both need |
| The connector against the real service, idempotency across a restart | **proven** | `tests/adapters/connectors/test_repository_live.py` against `Jersyfi/taktus`: a branch, a pull request (#12), a comment and a label, each requested twice by two connectors with no shared memory — one record each, the second answer replayed. The test closed the pull request and deleted the branch afterwards |
| P-02 reads the issue and its comments, checks it | done | run `run_ce35f408de39df86992f` (below): two reads through the connector, two API requests, the `exact` check passed |
| P-02 derives the criteria (`llm`) | **not run** — no model credential | the step failed with `no model is configured for the purpose 'reasoning' (TAKTUS_MODEL_ENDPOINT, TAKTUS_MODEL_NAME)` and the run escalated at that boundary, as designed |
| P-02 writes the criteria | not reached | |
| P-03 reads and checks | done | run `run_bd21d395b960c814e5e4`: the `exact` check refused the issue, correctly — P-02 had not written the criteria |
| P-03 implements (`worker`) | **not run** — no coding-agent credential | |
| P-03 branches, waits for the pipeline, verifies, opens the pull request, labels | not reached; **proven against the fakes** | `tests/integration/test_dev_orchestration.py`: the same two bundles, the same command line, the reference connector and the coding worker as processes, with the repository service, the model endpoint and the coding agent faked — one comment, one branch with the worker's files on one marked commit, one pull request with one label, three egress entries |

Nothing was written to the repository by the two process runs: both stopped before their first
outward step. The only writes were the live idempotency test's, which it removed.

## The runs

State: in memory with a file snapshot (no database was started for this). The identity:
`idn_owner`, provisional (DEC-0013). The connector: the reference connector as a process,
`--repository Jersyfi/taktus`, the token in its environment from the session's own login and
nowhere else; its log names operations and counts, never a value.

**P-02, first attempt — `run_52689a582890ecd03a30`, escalated at `admit`.** The check
`the issue body does not mention acceptance criteria` refused the issue, because the issue's
last paragraph says "P-02 adds the acceptance criteria". The check looked for the phrase; it
should have looked for the *section*. Corrected in the bundle in the same session: the
condition on the body is now `(?m)^## Acceptance criteria`, the heading P-02 itself writes
and P-03 reads.
Ledger: 12 entries, chain verifies; consumption: 2 requests.

**P-02, second attempt — `run_ce35f408de39df86992f`, escalated at `refine`.**

```
   1 read-issue           rule       sourced   succeeded  quota 1.0 artifacts: result
   2 read-comments        rule       sourced   succeeded  quota 1.0 artifacts: result
   3 admit                rule       exact     succeeded  artifacts: result
   4 refine               llm        sourced   failed     — no model is configured for the purpose 'reasoning' (…)
   5 compose-comment      rule       sourced   planned
   6 write-criteria       rule       sourced   planned

ledger  15 entries of this run, chain of 27: verifies
provenance  3 records of this run, one per completed step: chain verifies
consumption  quota 2.0
budget       quota 60.0
```

The provenance of `read-issue` names its source — `repository.issues.read {"number": 11}`,
capability `repository.issues`, the moment, and the digest of what the service answered
(`sha256:fdce0a38…`) — so that "since when has this been wrong?" is answerable for the issue's
text as it was read.

**P-03 — `run_bd21d395b960c814e5e4`, escalated at `admit`.** Reads as above, the context
composed, and the `exact` check refused: `'# make doctor does not report git, …' does not match
'(?m)^## Acceptance criteria'`. Correct: the criteria were never written. Fourteen steps
planned, four ran, nothing outward.

## Where it needed a hand

1. **The issue was written by the session**, not by a person: there was no open issue in the
   repository. It is a genuine gap all the same.
2. **The repository token came from the developer's own login** (`gh auth token`), handed to
   the connector process through its environment for the length of the run. The owner's run
   should use a token issued for the identity Taktus acts as, with contents and pull requests
   write, issues read — no more (`CREDENTIALS.md`).
3. **No model endpoint, no coding-agent credential.** Both stopped the run at a step boundary
   with a reason naming the setting; nothing was left half done.
4. **The pipeline on a branch.** P-03 reads the pipeline's verdict before it opens the pull
   request, which needs CI to run on a plain push. `.github/workflows/ci.yml` gains
   `push: branches: [main, "taktus/**"]` in this pull request — so the first full P-03 run can
   only pass its `verify` step after this pull request is merged, or on a branch where CI is
   configured that way.

## What was uncomfortable

- **A phrase is not a section.** The first check was wrong in a way a test against the fake
  could not find, because the fake's seed issue does not talk about acceptance criteria in
  prose. The real issue did. One live read found it; the fixtures now say the section.
- **Three credentials for one command.** The repository token, the coding agent's key or
  session token, the model endpoint's key: three parameters, three files, before
  `tools/first_run.sh` does anything. That is the honest count for a run that reads a
  repository, thinks and writes code; it is also the first thing a second tenant will feel.
- **A failed check quotes the value it checked.** The run's reason — printed by `taktusctl`,
  never in the ledger — carries the first eighty characters of the issue body. Useful for the
  person, and content on the command line all the same.
- **A second P-03 run for the same issue collides on the branch.** The branch is named by the
  issue (`taktus/issue-11`); a *new run* derives a new idempotency key, finds the branch with
  the first run's mark, and ends `conflict` — correct for the contract, inconvenient for the
  person, who has to delete the branch or resume the first run instead of starting a second.
  The resume is the right answer, and the escalation's last line says how.
- **Forty minutes of polling.** `wait-for-pipeline` asks the pipeline's state every 30 seconds
  for up to 2400 seconds: up to 80 requests of the run's 200. Enough for this repository's CI;
  an event (`pipeline_run.completed` reaches the intake already) would make the wait free.
- **The identity is provisional, and says so on every line.** `identity idn_owner (provisional:
  DEC-0013)` is right; it is also a reminder that whoever comments on a public issue is, once
  completed into a command, the operator.
- **The output is long.** 27 ledger lines for a run of four steps. Right for a first run that
  must be inspected line by line; wrong as the default once runs are routine.

## What the owner runs

```
tools/first_run.sh 11
```

with `REPOSITORY_TOKEN_FILE`, `CODING_AGENT_API_KEY_FILE` or `CODING_AGENT_SESSION_FILE`,
`TAKTUS_MODEL_ENDPOINT` and `TAKTUS_MODEL_NAME` (and `TAKTUS_CREDENTIAL_MODEL_API_KEY_FILE`
where the endpoint needs a key) in the environment or in `.env`. The script starts the connector
and the coding worker, runs P-02 and then P-03, prints every run with its ledger and its
provenance, and stops what it started. P-03 opens the pull request; CI decides; a person
merges. If P-02 has already written the criteria — as after a partial run — P-02 stops at its
check and the script stops with it; run P-03 alone with the four `--input`s its header shows.
