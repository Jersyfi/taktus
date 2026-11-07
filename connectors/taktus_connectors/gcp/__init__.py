"""The cloud operations connector: the connector contract v1 over Google Cloud.

Three capabilities of one project: `logs.query` over the logging API, `billing.costs` over the
billing export the data warehouse holds, `secrets.metadata` over the secret API, never a value.
This directory, its README and configuration are the only places that name the product.
Everywhere else it is the capability (CLAUDE.md §6, ADR-0150).

Run it: `python -m taktus_connectors.gcp --project <id>`. The modules: `declaration` is what it
declares, `api` how a request is made and authorised, `logs`, `billing` and `secrets` how each
API is asked and read, `operations` the table of them, and `server` how the shared MCP server
of `connectors/serving.py` serves it.
"""
