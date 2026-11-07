"""The site connector for one hosting service: the connector contract v1 over the Netlify API.

One capability, `deployment.sites`: a site read with the deploy it publishes, a deploy built
before published, and an earlier deploy put back. The interface is the service's REST API over
HTTP and JSON.

Run it: `python -m taktus_connectors.netlify`. The modules: `declaration` is what it declares,
`operations` how the API is asked, and `server` how the shared MCP server of
`connectors/serving.py` serves it.
"""
