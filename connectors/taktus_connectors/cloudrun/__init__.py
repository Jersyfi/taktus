"""The serverless connector: the connector contract v1 over the Cloud Run Admin API v2.

One capability, `deployment.workloads`, as the cluster connector serves it: a service read, its
image released as a new revision, the traffic put back on an earlier revision. The interface is
the API over HTTP and JSON, with an access token a service account key is exchanged for.

Run it: `python -m taktus_connectors.cloudrun`. The modules: `declaration` is what it declares,
`operations` how the API is asked, `auth` how a key becomes a token, and `server` how the
shared MCP server of `connectors/serving.py` serves it.
"""
