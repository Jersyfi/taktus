"""The feedback portal connector: the connector contract v1 over the Canny API v1.

The capability `feedback.posts`: the posts of a feedback portal read, a post created for a
customer and a customer's vote counted, both writes `marked`. This directory, its README and
configuration are the only places that name the product. Everywhere else it is the capability
(CLAUDE.md §6, ADR-0207).

Run it: `python -m taktus_connectors.canny`. The modules: `declaration` is what it declares,
`operations` how the portal is asked and read, and `server` how the shared MCP server of
`connectors/serving.py` serves it.
"""
