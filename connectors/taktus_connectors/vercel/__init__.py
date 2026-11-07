"""The site connector for one hosting platform: the connector contract v1 over the Vercel REST
API.

One capability, `deployment.sites`: a project read with the deployment its production serves, a
deployment built before promoted to production, and an earlier production deployment put back.
The interface is the platform's REST API over HTTP and JSON.

Run it: `python -m taktus_connectors.vercel`. The modules: `declaration` is what it declares,
`operations` how the API is asked, and `server` how the shared MCP server of
`connectors/serving.py` serves it.
"""
