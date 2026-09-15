# ADR-0012 — Licensing and repository visibility

**Status:** **open** — the owner decides. The reservation below applies until then.

## Context
An early draft copied the Business Source License from a sibling project. That was wrong: what is
taken from that project is the *way of working*, not the business model. The accounting unit for
Taktus is also still being worked out (ADR-0010).

At the same time the repository should be public from the start, so the work is visible while it
happens.

## Decision until further notice
- **Public, but no rights granted.** `LICENSE` is a reservation of all rights. Making the source
  visible is not the same as licensing it, and this is a normal arrangement for a preview phase.
- `NOTICE` states the intent: Fair Source or Source Available at the time of release, before
  `1.0.0`.
- **No third-party contributions are accepted.**

The last point matters more than it sounds. An accepted outside pull request belongs to its author
under unclear terms, and a later licence change would then need their agreement. So: licence and
contributor agreement first, then opening up.

## Recommendation for when the decision is made
Whatever model is chosen, **the contracts should be licensed more permissively than the core.**
Anyone building an adapter must be allowed to pass it on. Otherwise the community the adapter model
relies on never forms, and the "no lock-in" promise is not credible, because the alternative may not
legally be built.

## Consequence
Community adoption is deferred. A deliberate trade for a clean legal position, reversible at any
time.
