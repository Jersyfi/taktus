"""The social mentions connector: the connector contract v1 over the Mastodon REST API.

The capability `mentions.search`: the public posts of a social network that match a query,
each reduced to its address, its text and its moment, never its author. This directory, its
README and configuration are the only places that name the product. Everywhere else it is the
capability (CLAUDE.md §6, ADR-0207).

Run it: `python -m taktus_connectors.mastodon`. The modules: `declaration` is what it declares,
`operations` how the server is searched, and `server` how the shared MCP server of
`connectors/serving.py` serves it.
"""
