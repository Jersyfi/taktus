"""Owns models, agents, skills, connectors, blueprints, maturity.

In this version: the maturity of an adapter and the removal test that half of it rests on.
An adapter is `experimental`, `verified` or `reference` (`docs/architecture/contracts.md` §3);
*verified* needs a passed conformance suite and a passed removal test. The removal test is a
process Taktus runs for itself (`blueprints/self-operation/`): for one integration, withhold
it from the configuration, exercise the processes that use it, decide per process whether
something *broke* or only quality and cost *changed*, restore it, and record the result here
and in the ledger. The rules that decide a verdict are the domain service; what a run of the
process observed comes from outside the component, through the loopback connector.
"""
