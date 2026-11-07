"""The warehouse connector: the connector contract v1 over the BigQuery API v2.

One capability, `warehouse.queries`: a read-only query over the one dataset the connector is
configured with, the business's copy without personal fields (UC-03 B-9.02, UC-7.7). The
interface is the API over HTTP and JSON, with an access token a service account key is
exchanged for.

Run it: `python -m taktus_connectors.bigquery`. The modules: `declaration` is what it declares,
`operations` how the API is asked, `auth` how a key becomes a token, and `server` how the shared
MCP server of `connectors/serving.py` serves it.
"""
