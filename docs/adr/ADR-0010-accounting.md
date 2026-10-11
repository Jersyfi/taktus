# ADR-0010 — The Takt as a unit of orchestrated work

**Status:** **proposed**, amended 2026-09-30 (one breakdown, two tables), 2026-10-11 (compute seconds have a price too; a currency budget holds them, ADR-0005 fourth amendment) and 2026-10-11 again (the Takt is measured at weighting table 0, uncalibrated) — measured from `0.2.0`; how long data is collected before anything is
charged is decided later, based on real runs from both reference use cases

## Context
The usual models do not fit:

| Model | Why it fails here |
|---|---|
| per user | a business at level 4 has *fewer* people the more Taktus does. The model punishes the product's own success. |
| per run | a run lasts a second or eight hours. The number says nothing. |
| per token | measures language models only — one of six methods (ADR-0004), and the share is meant to fall. A price that drops with every improvement is not a business model. |
| per resource spend | the resources belong to the operator: their subscription, their key, their hardware. |
| flat rate | a family and a corporation pay the same. |

## Decision
**A Takt is a normalised unit of orchestrated work.** It measures what Taktus sets in motion,
regardless of who owns the resources consumed.

| Component | Measured as | Weight |
|---|---|---|
| language model use | normalised tokens × model class factor | high |
| ML and neural methods | compute seconds × resource class | medium |
| worker execution | compute seconds × resource class | medium |
| rule, statistics and connector steps | a small fixed value per step | very low |
| persistent state | storage × time | low |

Two quantities follow, as energy and power do in physics:
- **Takt consumption** (Takte) — work performed. For cost attribution, budgets, value ledger.
- **Takt rate** (Takte per hour, moving average) — what runs continuously. **The basis for charging.**

## Why the rate
- It measures what actually runs. An idle Taktus costs nothing.
- It grows with benefit, not with headcount.
- It is neutral between subscription, API key and own hardware. Charging is therefore fully
  separated from how the system is operated: the operator chooses per tenant and per model purpose,
  Taktus never fixes it and suggests when the other option would be cheaper.
- It falls when method selection improves. The vendor's interest then sits on the same side as the
  customer's benefit — which is not true of token billing.

## Condition
**The weighting table is public, versioned and recomputable from the ledger.** A sovereignty product
with a black-box bill is not credible. Any change to the weights is announced with an impact
estimate.

## Consequences
- **An untested model.** There is no precedent on the market. Therefore: measure from `0.2.0`,
  collect data across both reference use cases under varied conditions, and only then fix the
  formula. A price built on an uncalibrated formula burns trust once and for good.
- Open for the owner: the free threshold, peak versus average, tiers versus linear, and how
  measurement works in an air-gapped installation.

## Amendment — one breakdown, two tables (2026-09-30)

"Recomputable from the ledger" needs the ledger to hold what a figure is computed from. The
first live run showed it did not: money was reported per assignment and was not a function of
the tokens recorded, because caching and the mix of models inside a worker decide the bill
(`docs/runs/first-run.md` §2). What follows is built.

- **One breakdown.** Every consumption carries its language-model tokens per model and per
  price kind — uncached input, output, input read from a cache, input written to one
  (`contracts/shared/v1/Consumption.json`, `tokens_by_model`) — beside compute seconds per
  resource class, quota units and the steps per method. The accounting component meters a run
  from its `step.finished` entries into that one breakdown (`components/accounting`).
- **Two tables over it.** Money is the breakdown at a price table: versioned, never changed once
  used, and named by the run's budget statement through the digest of its document
  (`contracts/model/v1`, `PriceTable`; ADR-0005, third amendment). The Takt will be the same
  breakdown at a weighting table, once its weights are decided — which remains the owner's
  (M4.3). Neither figure is computed from the other.
- **Nothing unpriced counts as free.** A model or a kind a table does not price, and tokens
  recorded without the model that used them, are named beside the amount.

`taktusctl cost <run>` prints the breakdown and the money at the run's own table, or at another
table to compare.

## Second amendment — compute seconds have a price too (2026-10-11)

A price table may price a second of compute per resource class since ADR-0084, so that
maturation can compare a trained model with a language model. The cost of a run still priced
tokens only. The same table therefore gave two answers to "what did this cost". What follows is
built (#230, NTC-0184).

- **Money is the whole breakdown at the table.** The cost of a run is its tokens per model and
  kind plus its compute seconds per resource class, both at the one table the budget statement
  names. The report shows the two parts beside the total.
- **Nothing unpriced counts as free, compute included.** A resource class the table does not
  price is named. A table without `compute` gives the token amount and says that the compute
  seconds were not priced. A run held without a table names that when it used compute.

## Third amendment — the Takt is measured, not charged (2026-10-11)

The owner gave the first weighting table (DEC-0131, Option A) and the condition measuring must
meet (DEC-0132, UC-8.5 §2). What follows is built (#81, NTC-0190).

- **The table is a document in the repository.** Its shape is `WeightingTable`, beside the
  price table in `contracts/model/v1/Model.json`. The tables are under
  `contracts/model/v1/weighting-tables/`, one file per version, and the test of the Takt pins
  each file's digest, so that a published table cannot change. Version 0 is DEC-0131's table,
  marked `calibrated: false`. The table in force is the newest by `valid_from`; the operator
  does not choose it.
- **The model class is the operator's.** The table gives the factor of each class; which class
  a model is in is configuration (`TAKTUS_TAKT_MODEL_CLASSES`), as DEC-0131 says.
- **The run names the table it started at.** The budget statement names the weighting table in
  force by the digest of its document, and the model classes beside it. `taktusctl cost <run>`
  weighs the run's breakdown there and prints the Takte beside the money, in four parts:
  tokens, compute, steps, storage. `--weights` and `--model-classes` weigh it at another
  table, to compare.
- **What a row weighs.** Tokens per price kind per `unit_tokens`, times the model's class factor;
  compute per minute per resource class; finished steps of the methods the table names per
  step; MiB of state written. An `llm` step is weighed by its tokens, an `ml`, `neural` or
  `worker` step by its compute, not again by its number.
- **Nothing unweighed counts as zero.** A model in no class, a class or a kind without a weight,
  tokens without their model, compute of a class without a weight, and the steps of a method
  the table does not name — `human` and `wait` in version 0 — are named beside the figure.
- **The rate.** `taktusctl cost` without a run prints the tenant's Takte over the window of the
  table in force, 30 days for version 0, and the Takte per hour. Every step finished inside the
  window counts, weighed at the table its run started at.
- **"Uncalibrated" beside every figure** of an uncalibrated table, in the text and in `--json`.

## Where this promise ends

The Takt is proposed, not accepted: nothing is charged, the weights are version 0 and
uncalibrated, and the formula is fixed only after data from both reference use cases. A Takt
figure is a measurement, not a price (M4.2). "Recomputable from the ledger"
holds for what the ledger measures — tokens, compute seconds, resource class, step counts,
storage — and not for what a provider does not report; where money is reported per assignment
the Takt is still exact, because it derives from tokens and compute (ADR-0005). The Takt is
measured since the third amendment; a budget in Takte is not built, and admission holds tokens,
compute and currency only.

The breakdown holds what workers and models report. A worker that reports tokens without the
model that used them leaves them unpriced, and says so; a worker that reports money only when
an assignment ends reports it beside the computed figure, and the two may differ.

A budget in a currency holds compute money at the same table, during the run (ADR-0005,
fourth amendment, #232). Under a currency budget, compute the table does not price is refused,
not admitted as free. A run held to a compute budget alone can still use compute its table does
not price; its cost names that compute as unpriced. Quota units and storage have no price yet;
they stay outside the amount.

The Takt weighs storage as bytes written, because the ledger does not record how long state is
kept; "storage × time" waits for that measure. The rate is the tenant's average over the window,
not a peak; whether charging rests on a peak is still the owner's (Consequences). A run started
before a weighting table was in force has no Takt of its own: it is named, and can be weighed at
a table only on request, with the model classes given then. The window of the rate is the table
in force's, even for runs weighed at an older table.
