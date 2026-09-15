# Consumption and accounting

> Status: **proposal.** Measured from `0.2.0`. How long data is collected across both reference use
> cases before anything is charged is decided later, not fixed here. See
> [ADR-0010](../adr/ADR-0010-accounting.md).

---

## 1. Why a unit of its own is needed

| Usual model | Why it fails here |
|---|---|
| per user | a business at level 4 has *fewer* people the more Taktus does. The model punishes the product's own success. |
| per run | a run lasts a second or eight hours. The number says nothing. |
| per token | measures language models only — one of six methods, and the share is meant to fall. A price that drops with every improvement is not a business model. |
| per resource spend | the resources belong to the operator: their subscription, their key, their hardware. |
| flat rate | a family and a corporation pay the same. |

---

## 2. The Takt

**A Takt is a normalised unit of orchestrated work.** It measures what Taktus sets in motion,
regardless of who owns the resources consumed.

| Component | Measured as | Weight |
|---|---|---|
| language model use | normalised tokens × model class factor | high |
| ML and neural methods | compute seconds × resource class (CPU / GPU / accelerator) | medium |
| worker execution | compute seconds × resource class | medium |
| rule, statistics and connector steps | a small fixed value per step | very low |
| persistent state | storage × time | low |

Two quantities follow, as energy and power do:

- **Takt consumption** (Takte) — work performed. For cost attribution, budgets, the value ledger.
- **Takt rate** (Takte per hour, moving average) — what runs continuously. **The basis for charging.**

---

## 3. Why the rate

- It measures what actually runs. An idle Taktus costs nothing.
- It grows with benefit, not with headcount.
- It is neutral between subscription, API key and own hardware. **Charging is fully separated from
  how the system is operated.** The operator chooses per tenant and per model purpose; Taktus never
  fixes it and suggests when the other option would be cheaper or faster.
- It falls when method selection improves. The vendor's interest then sits on the same side as the
  customer's benefit — which is not true of token billing.

---

## 4. Subscription or key — always configuration

A model purpose (`triage`, `reasoning`, `embedding`, …) is bound to a supply mode per tenant:

```yaml
model_purposes:
  triage:    { supply: local,        adapter: ollama }
  reasoning: { supply: subscription, adapter: claudecode }
  coding:    { supply: subscription, adapter: claudecode }
  embedding: { supply: api_key,      adapter: openai_compatible }
```

Changing this changes no process definition. Taktus measures both supply modes, knows their limits —
a window for a subscription, a rate limit and a price for a key — and reports when the other would
be cheaper or faster.

---

## 5. The condition

**The weighting table is public, versioned and recomputable from the ledger.**

A sovereignty product with a black-box bill is not credible. Every operator must be able to recompute
their own Takt consumption from their own data. Any change to the weights is announced with an
impact estimate.

---

## 6. Calibration

The formula is a setting, not a measurement. Before anything is charged, data is collected from real
operation across **both reference use cases** under varied conditions: different method mixes,
subscription and key supply, local and remote models, small and large runs.

Only then are the weights fixed. A price built on an uncalibrated formula burns trust once and for
good.

---

## 7. Open

1. Where is the free threshold? Proposal: a Takt rate that safely covers private and family use, so
   that self-hosting stays effectively free for individuals.
2. Peak or average? Proposal: a 30-day moving average, so a single spike does not push anyone into a
   higher tier.
3. Tiers or linear? Tiers are more predictable and fit budgets better.
4. How is it measured without a network connection? In an air-gapped installation the measurement
   must stay local and be exportable.
