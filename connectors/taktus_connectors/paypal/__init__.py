"""The second payment provider connector: the connector contract v1 over the PayPal
Subscriptions API.

The capabilities `payments.subscriptions` and `payments.customers`, in the shape the first
payment provider connector answers them, so that a process reads either provider unchanged.
This directory, its README and configuration are the only places that name the product.
Everywhere else it is the capability (CLAUDE.md §6, ADR-0150, ADR-0206).

Run it: `python -m taktus_connectors.paypal`. The modules: `declaration` is what it declares,
`operations` how the subscriptions are asked and read, and `server` how the shared MCP server
of `connectors/serving.py` serves it.
"""
