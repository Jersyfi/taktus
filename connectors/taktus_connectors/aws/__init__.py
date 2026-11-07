"""The cloud connector: the connector contract v1 over three AWS APIs.

Three capabilities. `billing.costs`: an account's cost per day, by service, account or region,
as Cost Explorer reports it. `logs.query`: the events of a CloudWatch Logs log group that match
a filter pattern within a window. `secrets.metadata`: the metadata of the secrets Secrets
Manager stores, never a value. This directory, its README and configuration are the only places
that name the product. Everywhere else it is the capability (CLAUDE.md §6, ADR-0150).

Run it: `python -m taktus_connectors.aws`. The modules: `declaration` is what it declares,
`signing` how a request is signed, `api` where each API is and how one request is made,
`operations` how the costs are asked and read, `logs` the log query, `secret_store` the
secrets' metadata, and `server` how the shared MCP server of `connectors/serving.py` serves it.
"""
