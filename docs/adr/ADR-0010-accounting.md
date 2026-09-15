# ADR-0010 — The Takt as a unit of orchestrated work

**Status:** **proposed** — measured from `0.2.0`; how long data is collected before anything is
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
