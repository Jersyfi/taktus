# NTC-0028 — The live cap is held as tokens

**Mode entry:** M2.2
**Kind:** test-strategy
**Decided:** 2026-10-08
**Raised in:** the pull request that closes [#68](https://github.com/Jersyfi/taktus/issues/68)

## 1. What was decided

The coding worker now has a live test against its real agent:
`tests/workers/test_coding_worker_live.py`, run by the job `coding` of the workflow `live`. It
runs one process of one step through `taktusctl run`: the worker writes one file in an empty
workspace. The owner's cap per run, `LIVE_SPEND_CAP_USD` (USD 0.50, NEED-0012), is its budget.

The cap is held **in tokens, not only in money.** The worker learns what an assignment cost only
when the assignment ends. A money limit therefore cannot stop it while it runs; a token limit
can. So the test converts the cap:

- **The line** is the cap divided by a rate of USD 8 per million input tokens. At USD 0.50 that
  is 62 500 tokens. It is the run's token budget, beside the cap as the run's money budget.
- **The ceiling** is the line less a quarter: 46 875 tokens. The worker halts at the first step
  boundary where its running total has reached the ceiling. The call that crossed it has already
  run, and the quarter held back is there for that call, so that the run halts before the line.
- **The estimate** the worker is started with is the ceiling divided by the factor the run
  reserves for a worker with no history (twice the estimate, DEC-0034). The run then reserves
  exactly the ceiling.

The run's ledger, its output, the conversion, the bundle and the worker's log are the job's
artifact. The agent's own configuration directory is not, because it is not the repository's to
publish. Before anything is kept, the test looks for the key's value in every file and removes
and fails on any that holds it.

Without the key file or the cap the test skips and names what is missing. In the workflow,
`TAKTUS_REQUIRE_LIVE` turns that skip into a failure, and the job's first step fails when the
cap is not set.

## 2. The evidence

- The rate: the dearest rate the real agent was measured at, USD 0.833 for 110 615 tokens, about
  USD 7.53 per million, in attempt 3 of the first live run (`docs/runs/first-run.md` §2), rounded
  up. The tokens count every input kind, as the worker reports them, and the money includes the
  output.
- Why tokens: `workers/claudecode/README.md`, *Consumption* — "A budget that must hold while the
  agent runs is given in tokens" — and ADR-0005, third amendment, and DEC-0012.
- The held-back quarter: a call of the agent read 11 000 to 18 000 tokens in the first live run
  (110 531 to 257 289 tokens over 10 to 14 steps). A quarter of the line at USD 0.50 is 15 625.
- Measured against the stand-in, without the key: at full usage the stand-in's worker halted at
  55 012 tokens, past the ceiling of 46 874 and inside the line of 62 500, and the run halted
  with the limit as its cause (`test_an_agent_that_overruns_halts_at_its_ceiling_inside_the_line`).
  At a small usage the same harness finished, and the ledger showed the step admitted at its
  estimate and finished with its tokens (`test_the_harness_runs_end_to_end_against_the_stand_in`).

## 3. What was considered

- **The cap as a money budget alone.** Rejected: the run admits the step against the estimate,
  and the worker cannot be stopped by money while it runs. A run that overran would be found
  only after it had spent.
- **A list price per token of the agent's dearest model.** Rejected as the only source: the
  agent chooses its model and its caching, which a price list does not show; the measured rate
  includes both. The first run also showed that money is not a function of the tokens reported,
  varying 2.4 times against them. The provider workspace's monthly limit is the backstop behind
  the rate (NEED-0012, step 2).
- **No share held back.** Rejected: the worker yields by one call past its ceiling; with the
  ceiling at the line, that call would cross the cap's line.
- **The agent's own spend limit**, an option of its command line. Not taken here: the worker
  does not pass it, and adding it changes the worker, which is not this task. It would stop the
  agent inside a call, not at a boundary.
- **Calling the worker directly instead of through `taktusctl run`.** Rejected: only a run has a
  ledger, a budget statement and a reservation, and the issue asks for the run's ledger.

## 4. Which entry permits it

M2.2: "**A change of test strategy** and what the tests now cover." The test adds coverage of
the real agent and states how it holds the owner's cap. It does not raise or lower the cap,
which is the owner's (M3.10); it chooses how a test keeps inside it.
