"""The store reviews connector: the connector contract v1 over the App Store Connect API.

The capability `stores.reviews`: the customer reviews of an app, read without the reviewer,
and a public response written to one (ADR-0207). This directory, its README and configuration
are the only places that name the product. Everywhere else it is the capability (CLAUDE.md §6).

Run it: `python -m taktus_connectors.appstore`. The modules: `declaration` is what it declares,
`operations` how the reviews are asked and answered, and `server` how the shared MCP server of
`connectors/serving.py` serves it.
"""
