"""The store reviews connector of the second store: the connector contract v1 over the Google
Play Developer API.

The capability `stores.reviews`: the reviews of an app, read without the author, and a public
reply written to one (ADR-0207). This directory, its README and configuration are the only
places that name the product. Everywhere else it is the capability (CLAUDE.md §6).

Run it: `python -m taktus_connectors.googleplay`. The modules: `declaration` is what it
declares, `operations` how the reviews are asked and answered, and `server` how the shared MCP
server of `connectors/serving.py` serves it.
"""
