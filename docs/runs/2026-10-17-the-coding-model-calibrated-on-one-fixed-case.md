# The coding model calibrated on one fixed case — 2026-10-17

The calibration DEC-0200 allowed: three models of one provider at one level each, at most USD 15. It ran because stage 0 spends about USD 5.70 per merged pull request against USD 3 (#511). It spent **USD 2.64**.

## The fixed case

The coding step of P-03 for #481, "P-03 reads whether main is green before its coding step spends". It started from the commit Taktus's own run had cloned, `e4305cdb`, kept on the branch `calibration/issue-481`.

- **The copy run.** `p03-calibration@1` is P-03 version 19 cut to the steps the coding step needs: `read-issue`, `read-comments`, `context`, `implement`. It has no claim, no branch, no pull request and no outward write. Its workspace is cloned at the case's branch.
- **The model.** It was set for the coding worker's units through `CODING_AGENT_MODEL` in the instance's unit environment. After each change, the worker's conformance and the removal test ran again (`passed`, `changed`).
- **The evaluation, of each changeset.** It was applied to a copy of `e4305cdb`. Then `ruff check`, `ruff format --check`, `mypy`, and the 121 tests of `tests/integration/test_dev_orchestration.py`, `tests/integration/test_implementation_on_an_event.py` and `tests/components/process` ran.
- **The yardstick.** Taktus's own change for #481 (#503, Opus, P-03 version 16) passes the same evaluation: 5 files, +136 and −11 lines.

## Results

| Model | Run | Money | Input tokens | Output tokens | Files | Lines | Checks and 121 tests | A test of the new step |
|---|---|---|---|---|---|---|---|---|
| Opus 5.5 | `run_aac5f7b1722095fbd91a` | USD 1.84 | 1,701,199 | 15,044 | 5 | +110 −12 | pass | yes |
| Sonnet 5.5 | `run_303a4538456634189591` | USD 0.47 | 972,790 | 8,239 | 5 | +84 −8 | pass | yes |
| Haiku 5.5 | `run_b56f3dde8bdbc4ba7a0a` | USD 0.33 | 3,105,260 | 33,948 | 4 | — | pass | yes |

- **All three solved the case.** Each added one step that reads `main`'s verdict before the coding step and stops on a red one, plus a test that a red `main` stops the run.
- **Opus and Sonnet are nearly identical** in content, and leaner than the yardstick, which also waited while `main`'s run was still going.
- **Sonnet cost a quarter of Opus** and read the least: Opus 5.5 and Sonnet 5.5 cost the same per cached token read, and Sonnet needed fewer of them.
- **Haiku was the cheapest, but read three times what Sonnet read.** It needed more calls for the same result, which leaves it less room on a larger task, where the calls and with them the cache reads grow.

## What is not measured here

- **One case.** A larger task, such as #471, which cost Opus USD 8.90 without a usable change, is not in it.
- **The reviewer's judgement.** "Passes the checks and tests it touched, and tests the new step" is the measure here, not a person's review of the code.
- **Run-to-run variance.** The first live run measured a factor of 2.4 between attempts of one task.

## Spend

USD 2.64 of the USD 15 DEC-0200 set, for the three coding steps: 1.84 + 0.47 + 0.33. The worker's conformance run after each switch calls the agent on a small task too; its money is not counted here.
