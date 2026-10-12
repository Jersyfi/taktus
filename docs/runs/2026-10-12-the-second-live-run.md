# 2026-10-12 — The second live run: the budget meets a real service

Issue #74, part 1: P-03 on a small ready issue, against the real repository service, the real
coding agent and its real model, on the owner's workstation. The first live run since
2026-09-23 (`first-run.md`), and the first since the budget's third amendment (ADR-0005), the
maturity rule (ADR-0039) and the event reactions. Its measurements are the rows of *What the
next live run must measure* (`README.md`).

## What ran

| | |
|---|---|
| Issue | #250, `make verify-compose` submitting without an identity — a real defect found the day before |
| Process | P-03 Implementation, version 5, **at autonomy level 2** instead of its declared 4 (below) |
| Connector | the reference repository connector as Taktus's own app (ADR-0033) |
| Worker | the coding worker as a process on the workstation, its agent's default model |
| State | a fresh development state; the state of September could not be read (#283) |
| Budget | the bundle's: USD 5 and 200 quota units, raised to 400 on a resume (below) |
| Owner's cap | USD 3 for the live runs of #74 (DEC-0053) |

**Why level 2.** From level 3 a step runs only on an adapter at *verified* (ADR-0039,
NTC-0051), and a fresh workstation state has no adapter at any maturity: the run halted with cause
`maturity` at its first step. Making three adapters verified on a workstation would have cost a
second worker conformance suite against the real agent. At level 2 every step waits for a person;
the session confirmed each, with the owner's permission for the live runs. `tools/first_run.sh`
gained `--level`, `--approve` and `--quota` for it. Level 2 changes who starts a step, not what a
step reserves, consumes or records.

## The result

**Taktus opened pull request #274 as its own app**, closing #250: the coding agent fixed
`deploy/docker/verify.sh`, the run read the pipeline's verdict, and opened the pull request. It
needed four interventions by a person on the way, each a finding below.

## The measurements

### Row 1 — the budget under the new margin: estimate, reservation, actual

| Step | Estimate (admitted) | Reserved | Actual |
|---|---|---|---|
| `read-comments` | quota 10 | calibrated | quota 3 |
| `read-open-issues` | quota 20 | calibrated | quota 1 |
| `claim` | quota 3 | calibrated | quota 4 |
| `implement`, attempt 1 | tokens 60 000 / 6 000, USD 1.00 | calibrated | stopped after 7 min: tokens 925 229 / 370 reported, no money reported; about USD 1 spent (agent session: 1.86 M cache read, 0.23 M cache write, 13 465 output) |
| `implement`, attempt 3 | tokens 60 000 / 6 000, USD 1.00 | calibrated from attempt 1: tokens 925 229 / 370 | tokens 2 608 882 / 972, **USD 1.77**; agent session: 1.45 M cache read, 0.23 M cache write, 15 188 output |
| `create-branch` | quota 64 (192 reserved with the margin) | calibrated | quota 14 |
| `wait-for-pipeline` | quota 162 | — | quota 70, 17 minutes |
| `read-pipeline` | quota 2 | calibrated | quota 4 |

- **The coding step exceeded its estimate by a factor of 43 in tokens and 1.8 in money.** The
  worker's estimate is still a constant (`first-run.md` found 4.3×). The reservation of the
  third attempt was calibrated from the first, but on the undercounted output (#278).
- **A stopped coding assignment reported no money** (#277): attempt 1 cost about USD 1 that no
  budget counted. The run's currency budget held USD 1.77 of about USD 2.8 spent.
- **Tokens without their model** (#279): `taktusctl cost` could neither price nor weigh them.
- **The quota reservations over-reserve**: 192 reserved for 14 used by `create-branch`.

### Row 2 — a halt at a boundary on a real reservation

**Shown, on quota, not on tokens.** `create-branch` needed 192 units with 187 left: the step was
rejected by admission, the run halted with cause `limit` at the step boundary, nothing was
written. Resumed with the quota raised to 400 (a resume reads the bundle again), the step was
admitted and ran; the provenance chain has no gap. The halt the row asks for — a worker halting
at its own boundary on a **token** limit (W-14) — needs the second run of #74, which waits for a
budget beyond DEC-0053's USD 3: the first run spent about USD 2.8.

### Rows 3 and 4

On the instance: #75.

## Interventions and findings

| # | What happened | Issue |
|---|---|---|
| 1 | The September state could not be read: a traceback | #283 |
| 2 | No adapter is verified on a fresh state: the run halted at its first step with cause `maturity` | `--level` here; the instance's own way to verified is #87 |
| 3 | The worker client gave up on a working agent after three silences of a minute — the agent was running tests | #271, fixed by #272 |
| 4 | The resumed coding step could not clone into the workspace the first attempt left; a person moved the workspace aside | #280 |
| 5 | The stopped attempt reported no money | #277 |
| 6 | Output tokens undercounted twentyfold | #278 |
| 7 | Tokens recorded without their model | #279 |
| 8 | The agent took a record number `main` held and replaced its index row; the pipeline failed; a person renumbered | #281 |
| 9 | The pull request repeated its sections, and its closing section was stale an hour later; a person refreshed it and merged `main` into the branch | #282 |

## What it cost

About **USD 2.8** of the owner's USD 3 (DEC-0053): about USD 1 for the stopped attempt, USD 1.77
for the one that finished, a few thousandths for the model check of the restored endpoint
(DEC-0019, 13 tokens). The agent ran on its default model, the largest of its family; a cheaper
model for the coding worker is a configuration (`CODING_AGENT_MODEL`) nobody has chosen.
