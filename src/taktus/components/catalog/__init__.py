"""Owns models, agents, skills, connectors, blueprints, maturity.

In this version: the maturity of an adapter and the two halves it rests on.
An adapter is `experimental`, `verified` or `reference` (`docs/architecture/contracts.md` §3);
*verified* needs a passed conformance suite and a passed removal test. The conformance half is
recorded by `RunConformanceHandler`, its one writer: the instance runs the suite of the adapter's
contract through the `Suites` port, against the endpoint its configuration resolves, and records
what it found in the same operation; a pass counts only for the configuration it names
(ADR-0044). The removal test is a
process Taktus runs for itself (`blueprints/self-operation/`): for one integration, withhold
it from the configuration, rehearse the processes that use it (ADR-0030), decide per process
whether something *broke* or only quality and cost *changed* — or record *untested* when no
process uses it — restore it, and record the result, with the configuration it was taken
under, here and in the ledger. The rules that decide a verdict are the domain service; what a
run of the process observed comes from outside the component, through the loopback connector.

**Skills** (ADR-0162): a version of a `SKILL.md` kept beside its file — origin, stage, rounds,
measurements — moving draft, evaluated, approved, production, retired, every stage in the
ledger; approval by a person at levels 1 to 3 and by rule at level 4 after n passed rounds, with
a floor no configuration goes below (DEC-0028, NTC-0246); a fallback by rule. Whose own use a
draft was drawn from is kept apart from every score (`SkillOwnership`).

**Shared agents** (ADR-0163): one versioned core and role profiles versioned apart that only
narrow it; a profile resolved from the caller's roles, the fewest rights where several apply; a
core change held until every profile's evaluation passed.
"""
