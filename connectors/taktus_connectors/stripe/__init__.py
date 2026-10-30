"""The payment provider connector: the connector contract v1 over the Stripe REST API.

The capability `payments.subscriptions`: the subscriptions a payment provider holds, read with
the fields a match against the product's entitlements needs, and no personal data. This
directory, its README and configuration are the only places that name the product. Everywhere
else it is the capability (CLAUDE.md §6, ADR-0150).

Run it: `python -m taktus.adapters.driven.connectors.stripe`. The modules: `declaration` is what
it declares, `operations` how the subscriptions are asked and read, and `server` how the shared
MCP server of `connectors/serving.py` serves it.
"""
