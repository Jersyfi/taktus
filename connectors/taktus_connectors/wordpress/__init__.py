"""The website connector: the connector contract v1 over the WordPress REST API.

One capability, `website.posts`: a post drafted, read, and published once a person released
it.

Run it: `python -m taktus_connectors.wordpress`. The modules: `declaration` is what it declares,
`operations` how the API is asked, and `server` how the shared MCP server of
`connectors/serving.py` serves it.
"""
