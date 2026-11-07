"""The secret store connector: the connector contract v1 over HashiCorp Vault's KV version 2.

The capability `secrets.metadata`: what a secret store says about its secrets — when each was
created and when its current value was set — and never a value. This directory, its README and
configuration are the only places that name the product. Everywhere else it is the capability
(CLAUDE.md §6).

Run it: `python -m taktus_connectors.vault --target https://vault.example:8200`. The modules:
`declaration` is what it declares, `operations` how the metadata is listed and read, and
`server` how the shared MCP server of `connectors/serving.py` serves it.
"""
