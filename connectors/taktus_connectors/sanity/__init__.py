"""The website connector: the connector contract v1 over the Sanity HTTP API.

One capability, `website.posts`: a post drafted as a draft document, read, and published once a
person released it — the operations the WordPress connector serves, under the same names.

Run it: `python -m taktus_connectors.sanity`. The modules: `declaration` is what it declares,
`portable` how a post's HTML becomes Portable Text, `operations` how the API is asked, and
`server` how the shared MCP server of `connectors/serving.py` serves it.
"""
