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

## 5a. One breakdown, two tables — built

What is built of this page (ADR-0010, amendment of 2026-09-30):

- **The record.** Every step's consumption carries its language-model tokens per model and per
  price kind — uncached input, output, cache read, cache write — beside compute seconds per
  resource class and quota units (`contracts/shared/v1/Consumption.json`, `tokens_by_model`).
- **The meter.** `components/accounting` builds one breakdown of a run from its `step.finished`
  entries: tokens per model and kind, compute per class, quota, steps per method, and the money
  workers reported themselves.
- **Money.** The breakdown at a versioned price table (`contracts/model/v1`, `PriceTable`), the
  one the run's budget statement names by digest: `taktusctl cost <run>` prints it, or prices
  the same breakdown at another table with `--prices`. A new table version is made by an
  explicit act, never fetched at run time: `taktusctl prices import <file>` turns an open price
  list in LiteLLM's shape into a table file — input, output, cache read and cache write per
  model — and lists the entries it could not map; tiered prices are not read (#327). The money is the tokens per model and
  kind plus the compute seconds per resource class, with both parts shown (ADR-0010, second
  amendment). A model named with a snapshot date, as a coding agent names it, is priced at
  the table's entry for the undated name where the table has none for the dated one; its
  model class is found the same way (`contracts/model/v1` §6). A model, a kind or a resource
  class without a price is named, never counted as free; so is a table that prices no compute. A currency budget holds compute money at the
  same table during the run, and refuses compute the table does not price (ADR-0005, fourth
  amendment). A run held with an uncalibrated margin an operator set below the floor
  says so beside its money, as its budget statement does (DEC-0047).
- **The Takt.** The same breakdown at a weighting table (ADR-0010, third amendment). The
  tables are in the repository, `contracts/model/v1/weighting-tables/`, one file per version,
  in the shape `WeightingTable` of `contracts/model/v1/Model.json`. Version 0 is the owner's
  first table (DEC-0131), uncalibrated. A run's budget statement names the table in force when
  it started by digest, with the model classes the operator set (`TAKTUS_TAKT_MODEL_CLASSES`).
  `taktusctl cost <run>` prints the Takte beside the money, or at another table with
  `--weights`; without a run it prints the tenant's Takte over the table's window and the rate
  per hour. A quantity the table does not weigh is named, never counted as zero, and every
  figure of an uncalibrated table says so (UC-8.5). The weights stay the owner's (M4.3);
  section 6 says when they are fixed.

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
2. Peak or average? Measured as a 30-day moving average, the window of table 0 (DEC-0131); what
   charging rests on stays open until a price exists.
3. Tiers or linear? Tiers are more predictable and fit budgets better.
4. How is it measured without a network connection? In an air-gapped installation the measurement
   must stay local and be exportable.
