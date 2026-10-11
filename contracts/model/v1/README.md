# Model contract v1

A language model is reached through this contract: a prompt in, a completion out, with what it
used — and, before the call, what the adapter can say about it. **A budget promise over a model
is only as strong as the provider permits** (`docs/vision/principles.md`, principle 8); this
contract is where an adapter says how strong that is.

| File | Contents |
|---|---|
| [`Model.json`](Model.json) | the declaration, the usage of one call, the price table and the exchange the checks judge, as JSON Schema 2020-12 |
| [`examples/`](examples/) | valid examples per definition, and the must-fail fixtures for the checks below |

On the wire an adapter speaks whatever its provider speaks. The one adapter this repository
ships speaks the chat-completions dialect most endpoints answer
(`src/taktus/adapters/driven/models/openai_compatible`); the core's side is the model port
(`src/taktus/ports/model.py`), held to this schema by `tests/contract`. `make gate-contracts`
checks the schema and every example.

---

## 1. Reaching a model

A process reaches a model by **purpose** — `reasoning`, `triage` — never by product.
Configuration binds a purpose to an adapter and a model; the ledger carries the adapter's
identifier, and the provenance of every answer carries the model that gave it (ADR-0021).

## 2. The declaration

Every adapter declares its `Calculability`, constant for its configuration:

| Field | Values | What it says |
|---|---|---|
| `input_count` | `exact` · `upper_bound` · `estimate` · `none` | how the adapter counts a prompt's input tokens before the call: equal to the bill, never below it, on either side of it, or not at all |
| `output_cap` | `hard` · `soft` · `none` | whether the provider holds the output limit a call sets, reasoning included; `soft` where reasoning or tool output may lie outside it |
| `usage_kinds` | any of `input`, `output`, `cache_read`, `cache_write` | the price kinds the provider reports per call; money is recomputable exactly only from kinds that are reported |
| `billing` | `per_token` · `per_window` · `per_hardware_time` | how the provider bills: by the tokens of each call, as a share of a subscription's time window, or as time on hardware the operator owns or rents |
| `provider_limit` | `hard` · `alert` · `none` · `unknown` | what the provider enforces itself over a month; information only, never relied on |
| `evidence` | text | where the evidence for the declaration is written down, with its date |

An adapter declares no more than its provider permits. The evidence of 2026-09-30, provider by
provider, is `docs/research/2026-09-30-what-providers-allow.md`.

**What Taktus derives from it.** When a budget is set, the run records, per limited kind, how
it will be held — exactly per step, as an estimate, only as a share of a time window, or not at
all — and why (`budget.set`, ADR-0005 third amendment):

| The declaration | A budget in a currency |
|---|---|
| `billing: per_window` | **cannot be enforced**; only a share of the window can |
| `billing: per_hardware_time` | cannot be enforced as money; hold it with a compute budget |
| no price in the price table | cannot be enforced: the step's cost cannot be computed |
| `input_count: estimate` or `none`, or `output_cap` not `hard` | held as an estimate: one step may exceed it |
| otherwise | held per step: bounded before, measured after |

## 3. Before the call

**The count.** An adapter counts a prompt's input before the call as it declares. A step whose
model declares `none` has no estimate and is refused, not admitted (ADR-0005).

**The dialect's upper bound.** The chat-completions dialect has no endpoint that counts. Over
it, the count is an upper bound: **one token per UTF-8 byte of every message's content, sixteen
per message, sixteen per request.** A tokenizer that works on bytes emits at most one token per
byte, and a chat template adds a few per message. The bound over-reserves, and it is safe.
The adapter computes exactly this, and `tests/contract` holds the two to each other.

**The output.** A call sets a limit on its output. With `output_cap: hard` the provider never
produces more, reasoning included, and the step's output estimate is that limit.

## 4. Conformance

```
uv run taktusctl conformance run --contract model/v1 --endpoint <base URL> --model <name> \
    [--declaration declaration.json] [--credential VARIABLE]
```

The suite validates the declaration, then makes two calls: a short one, and one that asks for
far more than a limit of sixteen tokens. Without `--declaration` it judges the shipped
adapter's default declaration. The credential is read from the environment by the name given
and sent as a bearer value; it is never printed.

| # | Check |
|---|---|
| M-01 | the declaration validates and names its billing basis |
| M-02 | a declared input count holds: `exact` equals what the provider reports, `upper_bound` is never below it |
| M-03 | a declared hard output limit holds: the output never exceeds the limit the call set |
| M-04 | every price kind the declaration names is reported, and the kinds add up to the totals |

A declaration that claims no hard limit gives M-03 nothing to hold, and the report says so.
How to run it by hand and keep its report, and how an instance records it, is
[CONFORMANCE.md](CONFORMANCE.md).
**Fixtures.** `examples/exchange/valid/` holds calls that keep their declaration;
`examples/exchange/invalid/M-NN-*.json` breaks exactly the check it is named after. An
exchange fixture is schema-valid; what makes it invalid is a rule between its parts, which the
suite applies (`src/taktus/conformance/model/rules.py`) and `tests/conformance` holds to the
fixtures. `examples/calculability/invalid/M-01-*.json` fails by schema.

## 5. After the call

A completion reports its input and output tokens in total and, as far as the provider reports
it, by price kind: uncached input, input read from a cache, input written to one, output. The
run records them per model in the step's consumption (`contracts/shared/v1/Consumption.json`,
`tokens_by_model`), so that money follows from the record.

## 6. The price table

A `PriceTable` prices each kind of each model per `unit_tokens` tokens, in one currency, with
its source and the date it is valid from. **A version never changes once used**: a new price is
a new version. The run's budget statement names the table by the digest of its document, so
that `taktusctl cost <run>` recomputes the money at the prices the run was held to. A kind a
table does not price is unpriced, never free. The operator configures the table
(`TAKTUS_PRICE_TABLE`); the repository ships no prices, because they are a provider's and
change without notice.

A table may also price a second of compute per resource class, under `compute`. That is what a
step on a worker costs, so that a trained model's cost per case can be compared with a language
model's at the same table (ADR-0084). A class without a price is unpriced, never free. The field
is optional; `taktusctl cost` prices tokens only.
