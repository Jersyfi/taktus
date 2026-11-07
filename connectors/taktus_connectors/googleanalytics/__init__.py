"""The analytics connector: the connector contract v1 over the Google Analytics Data API v1beta.

One capability, `analytics.reports`: a report of one property's figures, aggregated by the
dimensions a call names, never by a person (UC-03 B-9.02, UC-7.7). The interface is the API over
HTTP and JSON, with an access token a service account key is exchanged for.

Run it: `python -m taktus_connectors.googleanalytics`. The modules: `declaration` is what it
declares, `operations` how the API is asked, `auth` how a key becomes a token, and `server` how
the shared MCP server of `connectors/serving.py` serves it.
"""
