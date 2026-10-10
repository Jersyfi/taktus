# DEC-0131 — The first weighting table of the Takt

**Category:** NON-BLOCKING
**Mode entry:** M4.3
**Raised in:** the pull request that raises the requests issue #81 needs, while checking #81 again as P-02 would
**Issue:** [#176](https://github.com/Jersyfi/taktus/issues/176)
**Needed by:** before #81 is built; the roadmap places it in `0.2.0`
**Provisional answer:** none is chosen for you: this is your own question (mode 4). Until you answer, #81 is not ready, and the Takt is not measured; money and the consumption breakdown are measured as today.

## 1. What this is about

The **Takt** is the unit Taktus is meant to be paid in one day. It measures how much work Taktus
set in motion, whoever owns the computers and models that did it. Nothing is charged yet. The
roadmap says the Takt is **measured, not yet charged**, from version `0.2.0`, so that real data
exists before any price is fixed.

Every step Taktus runs already records what it used: language-model tokens per model and per kind
(input, output, input read from a cache, input written to one), seconds of compute per class of
machine, quota units, and how many steps of each method ran. Money is already computed from that
record with a price table. The Takt would be computed from the same record with a **weighting
table**: how many Takte one unit of each quantity is worth.

That table has no numbers yet. The design gives each part only a rough rank: language models
*high*, machine learning and workers *medium*, stored state *low*, rule and connector steps
*very low*. The numbers are yours.

## 2. Why you are being asked

Entry M4.3 of `docs/decisions/anchors.taktus.md`: the accounting basis — the Takt, its weights and
what is charged — is the owner's. This request carries data and no recommendation (DEC-0045).

**Sources checked:** ADR-0010 and its amendment (the Takt, the ranks, the condition that the table
be public, versioned and recomputable from the ledger), `docs/architecture/accounting.md` §2 to §7
(the components, the calibration rule, the open questions, a proposed 30-day window), the vision
(principle 8, repeatability and cost control; principle 13, no lock-in), both anchor pages
(`anchors.md` and `anchors.taktus.md`, which place the weights under M4.3), and the register — no
decision has set a weight. None of them gives a number.

## 3. What you must decide

With which first weighting table, if any, does Taktus measure the Takt from `0.2.0`?

## 4. What you need to know to decide

- **"Uncalibrated."** ADR-0010 says the weights are fixed only after data from real operation of
  both reference use cases. A first table is therefore a starting point, not a price. Measuring
  with it shows what the numbers would be; it charges no one. It would be marked as uncalibrated
  wherever a figure appears.
- **What a table must satisfy.** It is public in the repository, versioned, never changed once
  used — a change is a new version, announced with what it would have changed — and every figure
  can be recomputed from the ledger with it (ADR-0010, *Condition*).
- **What the ledger can weigh today.** Tokens per model and kind; compute seconds per class;
  steps per method; bytes of state written. It does **not** record how long state is kept, so
  "storage × time" can be weighed only as bytes written until that is measured.
- **The rate.** Charging would rest on the Takt *rate*, Takte per hour, as a moving average. The
  accounting page proposes a 30-day window, so that one spike does not move anyone up a tier.
  The window is part of the table's version.
- **Where the scale comes from.** Any unit works; what matters is the ratio between the rows. One
  common anchor is that 1 Takt equals the work of about 1,000 output tokens of a mid-sized model.
- **Cost.** Building the measurement (#81) is the same effort whatever the numbers are; they are
  one document.

## 5. Options

### Option A — the candidate table below, version 0, marked uncalibrated

- **Meaning:** Taktus measures with this table from `0.2.0`, and every Takt figure says
  "uncalibrated, version 0".

  | Row | Unit | Takte |
  |---|---|---|
  | language model, output | 1,000 tokens | 1.0 × the model's class factor |
  | language model, uncached input | 1,000 tokens | 0.25 × class factor |
  | language model, input written to a cache | 1,000 tokens | 0.3 × class factor |
  | language model, input read from a cache | 1,000 tokens | 0.025 × class factor |
  | model class factor | per model, set by the operator | small 0.25 · medium 1 · large 4 |
  | compute, ML, neural and workers | 1 minute | cpu.small 0.1 · cpu.large 0.4 · gpu.small 2 · accelerator.large 8 |
  | rule, statistics and connector steps | 1 step | 0.01 |
  | state written | 1 MiB | 0.001 |
  | rate window | — | 30-day moving average of Takte per hour |

  The ratios follow the ranks of ADR-0010; the token rows follow the ratio providers commonly
  price input, cache and output at.
- **Consequence:** data from the first real runs exists in Takte; the table is replaced by a
  calibrated one before anything is charged.
- **Reversibility:** cheap; a new version replaces it, and the ledger recomputes old runs at it.

### Option B — your own numbers, in the same shape

- **Meaning:** you give the numbers, or change some rows of Option A. The rest is as Option A.

### Option C — no table until data exists

- **Meaning:** `0.2.0` records the breakdown only, as today; the Takt is computed first when the
  data of both reference use cases exists, at the earliest `0.5.0`.
- **Consequence:** the roadmap's `0.2.0` item "Takt measurement" moves; #81 closes as not needed
  now. The first Takt figures later are computed from the ledger retroactively, so no data is
  lost.

## 6. What is blocked

#81 waits. Nothing else does: money, budgets and the breakdown work without the Takt.

## 7. How to answer

"DEC-0131: Option A.", "DEC-0131: Option B." with the numbers, or "DEC-0131: Option C." in the
issue. A free-text answer is read back as an interpretation and confirmed before it is acted on.
