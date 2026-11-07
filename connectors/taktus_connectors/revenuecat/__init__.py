"""The in-app subscription connector: the connector contract v1 over the RevenueCat REST API v2.

The capabilities `payments.subscriptions` and `payments.customers`, in the shape the first
payment provider connector answers them, over the subscriptions an app sells through the app
stores and the web. This directory, its README and configuration are the only places that name
the product. Everywhere else it is the capability (CLAUDE.md §6, ADR-0150, ADR-0206).

Run it: `python -m taktus_connectors.revenuecat --project <id>`. The modules: `declaration` is
what it declares, `operations` how the subscriptions are asked and read, and `server` how the
shared MCP server of `connectors/serving.py` serves it.
"""
