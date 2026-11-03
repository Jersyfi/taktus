# ADR-0148 — Where a process spends is read per step from the ledger, and two runs are set side by side

**Status:** accepted · extends ADR-0005 (budget and consumption) and ADR-0010 (accounting) · issue #449, DEC-0200 answer 3

## Context

The owner asked to see where a process spends: per step, and for each `llm` and `worker` step
the tokens apart by what they cost — plain input, cache writes, cache reads, output — the turns,
and what a compression saved (DEC-0200, answer 3). A change such as a compression or another
model is adopted only when two runs of the same task show it is better.

The ledger already records each step's tokens per model and price kind (`tokens_by_model`), and
money is recomputed from them at the run's own price table (`taktusctl cost`, ADR-0005 third
amendment). It records neither the turns of an agent nor a compression. The figures exist only
for a whole run. Nothing compares two runs.

## Decision

### 1. The consumption carries turns and a compression
`contracts/shared/v1/Consumption.json` gains two optional properties beside the quantities:

- `turns`: the calls to a language model an agent made within the step.
- `compression`: `before` and `after`, the input tokens the step would have sent without the
  compression and what it sent.

Neither is priced or limited. Neither alone makes a consumption: a record of turns without a
quantity is refused. The change only adds, so `v1` stays `v1` (ADR-0019). A worker reports them
in `consumption.reported` like every quantity, and the run sums them over the step's events.
The coding worker counts one turn for each of the agent's messages that led to a call.

### 2. Spend is read per step from the ledger
The accounting component meters each step's `step.finished` entries apart (`meter_by_step`)
and prices each step at the price table the run's budget statement names. Three questions are
answered from those records:

- **one run, by step**: each step's tokens by kind, turns, compression, compute seconds, money,
  its outcome and the digest of its result;
- **a process over a window**: the same per step, summed over every run of the process whose
  steps finished in the window, the money summed per currency;
- **two runs side by side**: both runs by step, and per step the difference in money, tokens and
  turns, and whether both produced the same result digest. Where the runs are of different
  processes or priced at different tables, the comparison says so.

`taktusctl cost RUN --by-step`, `taktusctl cost RUN --against OTHER` and `taktusctl cost
--process ID --days N` print them, and `--json` gives the documents.

## Alternatives

- **A table of spend per step, written at each finish.** It would be a second record of what the
  ledger already holds, and it could disagree with it.
- **Price at today's table.** The figure would change when the configuration changes; the
  run's own table keeps a figure recomputable (ADR-0005).
- **Compare result quality by a score.** The evaluation cases of ADR-0134 score a step against a
  target. Two arbitrary runs have no target; the digest says whether the results are the same,
  and a comparison on scored cases is the model trial's (#448).

## Consequences

- The shared kernel's binding gains `Compression`, `Consumption.turns` and
  `Consumption.compression`; the contract binding test follows a property into an `allOf`.
- The meter of a run carries the turns and the compression summed.
- The web app and the owner's channel show these views since the amendment of 2026-10-28.

## Amendment — the web app and the owner's channel show it (2026-10-28)

Issue #449, the remainder. What the Consequences left waiting is built.

- **Takte per step.** Each step's meter is weighed at the weighting table the run's budget
  statement names. A run's and a process's spend carry the Takte beside the money, with
  `calibrated` or `uncalibrated`.
- **The HTTP surface.** `GET /runs/{id}/spend`, with `against` for a second run, and
  `GET /processes/{id}/spend?days=N`, through the one visibility predicate (ADR-0055 §5).
- **The web app.** A run's spend is two charts on one axis from zero: money per step, and
  tokens per step split by price kind. Two runs share one axis, each named in the legend. A
  process is read over 7, 30 or 90 days. The run and the process pages link there.
- **The owner's channel.** `spend <run>`, `spend <run> <other>` and `spend process <process>`
  answer in the owner's conversation, with the link to the same view in the web app
  (`composition/spend_in_channel.py`). Only for the owner and whom they named, only on runs they
  may see; the phrasebook carries the words in each language.

## Where this promise ends

- A figure is as complete as what the workers reported. A worker that reports no turns shows
  none, and its steps' turns read zero.
- A compression is recorded only where the worker that ran it says so. Taktus does not compress
  on its own here.
- The window of a process reads every `step.finished` of the tenant once, and then each run of
  the process in it; its cost grows with the tenant's ledger, not with the window.
- No figure names a person (principle 14). A run, a step and a process are what is measured.
- The channel reads a process over thirty days only; another window is the web app's.
- A chart draws what the ledger holds. A step whose money cannot be priced has no money bar, and
  says so; it is never drawn at zero.
