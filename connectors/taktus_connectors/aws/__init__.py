"""The cloud billing connector: the connector contract v1 over the AWS Cost Explorer API.

The capability `billing.costs`: an account's cost per day, by service, account or region, as the
provider's billing reports it. This directory, its README and configuration are the only places
that name the product. Everywhere else it is the capability (CLAUDE.md §6, ADR-0150).

Run it: `python -m taktus_connectors.aws`. The modules: `declaration` is what it
declares, `signing` how a request is signed, `operations` how the costs are asked and read, and
`server` how the shared MCP server of `connectors/serving.py` serves it.
"""
