# DEC-0188 — Whom Taktus serves, and the project as one tenant among others

**Category:** NON-BLOCKING
**Raised in:** the session of 2026-10-12 that reviewed the concept, when the owner corrected its reading of what a tenant is; recorded in the pull request of its own that records the answer
**Issue:** none; the owner stated it in conversation, and this record is the statement with what it changes
**Needed by:** 2026-10-12
**Written after the answer:** the owner stated it in conversation on 2026-10-12; the record was written from it; left out of the acceptance rate (DEC-0042).

## 1. What this is about

The review's first version took a department of a corporation to be a tenant of its own. The owner
corrected this in three points.

1. **A tenant may hold many departments**, and processes cross them inside the tenant.
2. **Customers decide how far and how large they use Taktus.** The range runs from a single
   person, a family and a small business to a large corporation. It also includes an *operator*:
   someone who provides Taktus to others, B2C or B2B.
3. **The Taktus project itself will later drive its own development and also run the licensing of
   its customers, their billing and whatever else belongs to that.** The project's own development
   must never limit how a customer uses Taktus. Nothing that concerns only the project may reach a
   customer.

The owner also asked how connectors and similar adapters could be offered to customers as a
collection that grows with a community. DEC-0190 answers that.

## 2. Why you are being asked

The vision is the owner's (M4.5): whom Taktus is for is written in `docs/vision/vision.md`. The
owner's statement adds operators to that table, so it is recorded as the owner's answer before
the vision changes.

**Sources checked:**
- `docs/vision/vision.md` *Who it is for*: it names individuals and families, small and medium businesses, enterprises and the public sector, but no operator.
- `docs/vision/personas.md`: its *Operator* is the person who gives commands, not an operator of an instance.
- ADR-0020 places a tenant inside one instance and does not say how large it may be.
- `anchors.md` and `anchors.taktus.md` separate product from project for anchors only.
- The register holds no decision on the project's place among tenants.

## 3. What you must decide

Whether the vision names operators who provide Taktus to others, and whether the project is a
tenant like any other, with nothing of it in the product.

## 4. What you need to know to decide

- **An operator** runs one instance for many customers, each a tenant. Today an instance reads
  its tenants from one environment variable, so the review's measurements show it does not scale
  to operators (DEC-0187, T1–T3). Most of that work lands in `2.0.0`.
- **One tenant among others** means the following. The project's settings, budgets measured on
  its runs, its process identifiers, its repository's layout, and its later licensing and billing
  are configuration or bundles of the project's tenant. None of it is code or a default of the
  product. The review found one default that broke this: the budget seed. It found more in help
  texts and the chart (#313).

## 5. Options

### Option A — both, as stated (recommended)

- **Meaning:** `docs/vision/vision.md` names operators and states the project's place; ADR-0092
  makes the rule architectural, with an architecture test (#313).
- **Consequence:** every later feature is read against all four kinds of customer.
- **Reversibility:** cheap for the wording; the rule protects customers and is not meant to move.
- **Why recommended:** the owner's statement.

### Option B — the vision unchanged, only the rule

- **Meaning:** ADR-0092 alone.

## 6. What is blocked

Nothing.

## 7. How to answer

"DEC-0188: Option A." or "DEC-0188: Option B."

## Outcome

**Decided:** 2026-10-12
**Answer:** Option A. "Within a tenant there can also be several departments, so that processes across them can be mapped there. To what extent and at what size Taktus is used later is decided by the customers who use Taktus and make it operable. For Taktus itself I can say that it later must both drive its own development and take care of the licensing of customers, billing and whatever else belongs to that. Customers can of course be the most diverse, from single persons, families and small companies up to large corporations or operators who provide Taktus for others, B2C or B2B." And: "The development of Taktus itself must not have the effect that customers cannot use Taktus as they want, so nothing that concerns only Taktus's own development may also land at customers." (the owner's words, translated)
**Reasoning given:** the statement itself.
**What it does not change:** the fourteen principles; ADR-0020's boundary between tenants and instances.
**Recorded in:** this pull request: `docs/vision/vision.md` (*Who it is for*), ADR-0092, the issues #313 and #354.
