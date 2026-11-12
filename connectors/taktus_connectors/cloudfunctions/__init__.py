"""The functions connector: the connector contract v1 over the Cloud Functions API v2.

One capability, `deployment.sites`: the source archive a function serves read, an archive its
own build uploaded released to it, an earlier one put back. A function has no image and no
replicas, so it is a hosted version, not a workload (ADR-0211, ADR-0269). The interface is the
API over HTTP and JSON, with an access token a service account key is exchanged for.

Run it: `python -m taktus_connectors.cloudfunctions`. The modules: `declaration` is what it
declares, `operations` how the API is asked, `auth` how a key becomes a token, and `server` how
the shared MCP server of `connectors/serving.py` serves it.
"""
