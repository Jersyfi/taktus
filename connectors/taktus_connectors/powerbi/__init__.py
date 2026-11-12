"""The business-intelligence connector: the connector contract v1 over the Power BI REST API.

The capability `bi.figures`: a figure of the organisation's business-intelligence tool, read by
one DAX query against one semantic model, so that a process can take it as an input or a
trigger (UC-5.7). This directory, its README and configuration are the only places that name
the product. Everywhere else it is the capability (CLAUDE.md §6, ADR-0150).

Run it: `python -m taktus_connectors.powerbi --tenant <directory tenant>`. The modules:
`declaration` is what it declares, `operations` how a query is asked and its rows read, and
`server` how the shared MCP server of `connectors/serving.py` serves it.
"""
