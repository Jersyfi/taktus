"""The metrics connector: the connector contract v1 over the Prometheus HTTP query API.

The capability `metrics.series`: a series read by a query, at one moment or over a range.
Many metrics stores answer the same query API; this directory, its README and configuration are
the only places that name it. Everywhere else it is the capability (ADR-0111).

Run it: `python -m taktus_connectors.prometheus --target http://metrics:9090`.
The modules: `declaration` is what it declares, `operations` how a query is asked and its
answer read, and `server` how the shared MCP server of `connectors/serving.py` serves it.
"""
