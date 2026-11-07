"""The forum mentions connector: the connector contract v1 over the Discourse API.

The capability `mentions.search`: the posts of a forum that match a query, each reduced to its
address, its excerpt and its moment, never its author — the shape the social mentions connector
answers in. This directory, its README and configuration are the only places that name the
product. Everywhere else it is the capability (CLAUDE.md §6, ADR-0207).

Run it: `python -m taktus_connectors.discourse`. The modules: `declaration` is what it declares,
`operations` how the forum is searched, and `server` how the shared MCP server of
`connectors/serving.py` serves it.
"""
