# ADR-0010 — The Takt as a unit of orchestrated work

**Status:** **proposed**, amended 2026-09-30 (one breakdown, two tables) — measured from `0.2.0`; how long data is collected before anything is
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

## Where this promise ends

The Takt is proposed, not accepted: nothing is charged, the weights are a first draft, and the
formula is fixed only after data from both reference use cases. "Recomputable from the ledger"
holds for what the ledger measures — tokens, compute seconds, resource class, step counts,
storage — and not for what a provider does not report; where money is reported per assignment
the Takt is still exact, because it derives from tokens and compute (ADR-0005). A budget in
Takte is enforced only once the Takt is measured (`0.2.0`).

The breakdown holds what workers and models report. A worker that reports tokens without the
model that used them leaves them unpriced, and says so; a worker that reports money only when
an assignment ends reports it beside the computed figure, and the two may differ.
