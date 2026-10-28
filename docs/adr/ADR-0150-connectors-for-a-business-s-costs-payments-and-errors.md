# ADR-0150 — Connectors for a business's costs, payments and errors

**Status:** accepted · builds on ADR-0024 (the connector contract), ADR-0111 (the shared
serving module) and ADR-0117 (a vendor's own server) · serves UC-03 §8, the first condition of
`1.0.0-beta` · issue #447

## Context

The first condition of `1.0.0-beta` is a stage-1 process of UC-03 running against real
connectors: the cost watcher (B-1.01) or payment reconciliation (B-6.01). UC-03 §8 lists the
capabilities stage 1 needs and has none of them: a cloud billing export, a model provider's
costs, error tracking, a payment provider (`docs/usecases/AF-03-software-operations.md`).

Issue #447 asks for a connector for each system a business names, usable by any tenant
(DEC-0201). The names of the second tenant's systems are the tenant's (NEED-0028), and no
connector here may identify it. So the products are chosen by how widely they are used, not by
who uses them.

Four facts shape the decision.

- A figure held `exact` may come only from `rule` or `statistics` (CLAUDE.md §4). A cost or an
  amount read in floating point is already wrong in its last digit.
- Several of these products ship a server on the protocol connectors use. #410 makes such a
  server the first candidate, behind the vendor connector and a manifest (ADR-0117). The vendor
  connector passes on the tool's structured answer, or `{"text": …}` where the tool has none.
- The cloud provider most widely used signs each request with a key pair, Signature Version 4.
  The contract hands a connector one credential value per call.
- Principle 14 forbids a metric about a named person. An error tracker's issue names the person
  it is assigned to.

## Decision

### 1. Five connectors, each named by capability

| Capability | Operations | Product | Directory |
|---|---|---|---|
| `billing.costs` | `billing.costs.daily` | AWS Cost Explorer | `connectors/aws/` |
| `models.costs` | `models.costs.daily` | OpenAI organisation costs | `connectors/openai/` |
| `models.costs` | `models.costs.daily` | Anthropic Admin API cost report | `connectors/anthropic/` |
| `errors.issues` | `errors.issues.list`, `errors.issues.read` | Sentry | `connectors/sentry/` |
| `payments.subscriptions` | `payments.subscriptions.list`, `payments.subscriptions.read` | Stripe | `connectors/stripe/` |

Every operation is of effect `read`. None has an outward effect, so none needs a key of its own
(ADR-0024). Each connector is served by `connectors/serving.py`, as the connectors over open
standards are. Each passes the connector conformance suite against a fake of its product's API.
The product's name stands only in the directory, its README and the fake's docstring.
`tests/architecture` refuses it everywhere else (NTC-0236).

### 2. Costs are one shape, in decimal text

`billing.costs.daily` and `models.costs.daily` answer the same shape: `currency`, `days` oldest
first, each day with its `groups`, `{group, amount}`, and its `total`, and `complete`. Every
amount is the decimal text the provider gave. A day's total is the exact sum of its groups,
computed in decimal arithmetic. A day in more than one currency is `unexpected`, because no rule
here converts. A provider that reports cents is turned into the main unit by moving the
decimal point, which loses no digit. One statistic reads them all (ADR-0151).

### 3. A direct connector where the vendor's server answers in text

#410 prefers a vendor's own server. These four connectors call the product's API directly
instead, for three reasons. The payment provider's and the error tracker's servers answer in
text meant for a language model; a match held `exact` needs the records as fields. The cloud
provider's server runs beside the caller with the caller's own profile, not with the requesting
identity's credential per call, which the contract requires (C-03). The model providers ship no
server for their costs. Where a vendor's server comes to answer with structured fields and a
credential per call, it becomes the candidate again, behind a manifest.

### 4. A key pair is one credential value

The cloud billing credential, `BILLING_KEY`, is one text, `<access key id>:<secret access key>`,
with `:<session token>` for temporary credentials. The connector splits it at the call, signs
with the secret half, and sends only the key id and the signature. No contract changes.

### 5. Nothing about a person is passed on

The error tracking connector never copies an issue's assignee or any other person's field into
its output. The payment connector passes a customer's identifier, never their name, address,
e-mail or payment method: matching an entitlement needs none of them.

## Alternatives

- **The vendors' own servers behind manifests (#410).** Rejected for these four, for the
  reasons of §3. The vendor connector stays for products whose servers fit.
- **The billing export's open format (FOCUS) instead of a provider's API.** It needs a storage
  bucket and a query engine at the business, and #441 covers open standards. It stays a later
  connector, not the first.
- **The second tenant's systems.** Refused by DEC-0201 and the tenant's confidentiality: a
  connector is product support for any tenant.
- **Numbers instead of decimal text.** A float cannot hold `0.1`, and a sum of floats drifts.
  An `exact` figure would be built on a wrong one.
- **Two credential parameters for the key pair.** The contract hands one value per call. A
  second reference would change the contract for one product.

## Consequences

- `src/taktus/adapters/driven/connectors/{aws,openai,anthropic,sentry,stripe}/`; the fakes
  `tests/fakes/cloud_billing_service.py`, `model_costs_service.py`, `cost_report_service.py`,
  `error_tracking_service.py` and `payment_service.py`; `tests/conformance/test_connector_v1_business.py` runs the suite
  and every fault against each.
- `CREDENTIALS.md`: `BILLING_KEY`, `MODEL_COSTS_TOKEN`, `ERRORS_TOKEN`, `PAYMENTS_TOKEN`.
  NEED-0035 and NEED-0036 ask for the first two on the project's own instance.
- Each is added to an instance by one entry of `TAKTUS_CONNECTORS`. S-01 tests each like any
  connector.
- `composition/shipped.json` lists the five, so a lack is classified against them (ADR-0118).

## Where this promise ends

Each connector is proven against a fake of its product's API that its tests own. No real
provider has been reached by them yet; NEED-0035 and NEED-0036 open that for two of them, the cost report first. A
change of a provider's API is found by a live run, not by these tests. The cloud billing
connector reads at most ten pages, the error tracker ten, the payment provider a hundred, and
each says `complete: false` where it stopped early. The cloud billing figures of the newest day
may still change: the provider marks such a day `estimated`. The model providers do not say
whether a day is closed, so their days are never marked. That the cost report gives cents is
read from its documentation and checked against the fake; a live run confirms it. A reading in more than one currency is
refused, not converted. The payment connector reads subscriptions only; payment reconciliation
also needs the product's entitlements, which no connector here reads yet. The connectors read;
none acts on a provider.
