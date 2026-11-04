"""The workload connector: the connector contract v1 over a Kubernetes API server.

One capability, `deployment.workloads`: a deployment read, its image released, an earlier
revision put back, its replicas set, in one namespace (ADR-0195). The interface is the
cluster's own API over HTTP and JSON, which every conformant cluster serves alike.

Run it: `python -m taktus_connectors.kubernetes`. The modules: `declaration` is what it
declares, `operations` how the API is asked, and `server` how the shared MCP server of
`connectors/serving.py` serves it.
"""
