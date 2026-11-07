"""The package licence connector: the connector contract v1 over the deps.dev API v3.

The capability `packages.licences`: the licences a public package index states for the exact
versions a dependency manifest pins. This directory, its README and configuration are the only
places that name the product. Everywhere else it is the capability (CLAUDE.md §6, ADR-0232).

Run it: `python -m taktus_connectors.depsdev`. The modules: `declaration` is what it declares,
`manifests` how a manifest's pinned versions are read, `operations` how the index is asked, and
`server` how the shared MCP server of `connectors/serving.py` serves it.
"""
