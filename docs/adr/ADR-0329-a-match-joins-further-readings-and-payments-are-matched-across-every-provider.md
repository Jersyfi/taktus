# ADR-0329 — A match joins further readings, and payments are matched across every provider

**Status:** accepted · extends ADR-0199 (the rule `match`), ADR-0206 (three payment providers in
one shape) and ADR-0311 (a step names its configured connector) · serves UC-03 B-6.01 ·
DEC-0239, DEC-0225, DEC-0226

## Context

B-6.01 matches the active subscriptions at the payment provider against the product's
entitlements. Every entitlement without a paid partner is a mismatch, and each is an incident.
The process read one provider per run. A business that takes payments at several providers —
a card processor, a wallet, an in-app subscription service — keeps all their entitlements in
one product. Read against one provider, every entitlement paid at another provider was named
"granted, not paid". The process raised false incidents every morning, or it had to be left
off.

The product's entitlement records name the customer by the paying provider's identifier
(ADR-0199 §2). They do not name the provider. So a filter of the entitlements by provider
would need a field the product does not give.

## Decision

1. **A side of `match` takes further readings.** `MatchSide.more` is a list of parts, each a
   step's whole result (`reading`, usually `{$from: step}`) and the path of its list
   (`select`). Their items join the side's `items` in the order named, before any entry is
   keyed. A reading of a step that was skipped by its `when` adds nothing. A reading without
   the named list, or with something else there, fails the rule; it is never read as empty.
2. **B-6.01, version 3, reads up to three providers in one run.** Its inputs `provider`,
   `second` and `third` name configured connectors (ADR-0311). Each is read by a step of its
   own; a step whose input is not given is skipped. The match joins all their subscriptions.
   Without `provider`, the first connector configured for the capability serves, as before.
3. **The match stays `exact`.** The joined lists are the providers' own readings. The rule is
   the same equality of customer and product.

## Alternatives

- **Filter the entitlements by provider.** The manifest's entitlement has no provider field.
  Adding one would require every tenant's product to answer it, and would still need one run
  per provider whose results nobody adds up.
- **One run per provider, the mismatches compared afterwards.** Each run would raise its false
  incidents first. Comparing runs is a step with nothing to compare against.
- **A rule `concat` before the match.** It would be a step of its own for one list. The join
  belongs to the match, whose result names every entry it read.
- **Let `$otherwise` stand in for a skipped step's result.** It would change how every
  reference is resolved, for one rule's need.

## Consequences

- `components/run/domain/model/work.py`: `MorePart`, `MatchSide.more`, and the references of a
  match include its further readings. `domain/service/rules.py`: `match` joins them.
  `application/service/execute_run.py` resolves them.
- `blueprints/software-operations/processes/B-6.01-payment-against-entitlement.yaml`, version 3.
- `tests/components/run/test_match_rule.py` proves the join, the skip and the refusal;
  `tests/composition/test_software_operations_providers.py` runs B-6.01 on a card processor, a
  wallet and an in-app subscription service at once, and alone.

## Where this promise ends

- **Every provider must be named.** A provider the run does not name is not read, and the
  entitlements it pays for are named granted and not paid. The run cannot know which providers
  the business uses; the tenant's version fixes them.
- **Three providers.** The bundle has three reading steps. A business with a fourth makes a
  version of its own with a fourth step.
- **One customer, two providers.** A customer who pays for the same product at two providers
  is a duplicate key and a mismatch, as any key seen twice is.
- **One credential parameter.** The three connectors read their key under one parameter, each
  in its own process with its own file (ADR-0311).
- **No live provider was asked.** Every provider is proven against a stand-in built from its
  published API (DEC-0225, DEC-0226).
