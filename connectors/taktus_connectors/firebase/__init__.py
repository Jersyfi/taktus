"""The site connector: the connector contract v1 over the Firebase Hosting REST API v1beta1.

One capability, `deployment.sites`: the version a site serves live read, a finalized version
released to it, an earlier one put back. The interface is the API over HTTP and JSON, with an
access token a service account key is exchanged for.

Run it: `python -m taktus_connectors.firebase`. The modules: `declaration` is what it declares,
`operations` how the API is asked, `auth` how a key becomes a token, and `server` how the
shared MCP server of `connectors/serving.py` serves it.
"""
