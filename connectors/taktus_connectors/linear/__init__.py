"""The task tracker connector: the connector contract v1 over the Linear GraphQL API.

The capability `tasks.items`: the open tasks of a workspace, read without their assignee, and a
reminder written on one of them, `marked`. This directory, its README and configuration are the
only places that name the product. Everywhere else it is the capability (CLAUDE.md §6,
ADR-0209).

Run it: `python -m taktus_connectors.linear`. The modules: `declaration` is what it declares,
`operations` how the tasks are asked and read, and `server` how the shared MCP server of
`connectors/serving.py` serves it.
"""
