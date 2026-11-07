"""The directory connector: the connector contract v1 over SCIM 2.0 (RFC 7643, RFC 7644).

The capability `directory.accounts`: the accounts of an organisation's directory, with whether
each is active and the groups, roles and entitlements it holds, and the groups with their
members. SCIM is an open standard, so this connector names no product.

Run it: `python -m taktus_connectors.scim --target https://idp.example/scim/v2`. The modules:
`declaration` is what it declares, `operations` how the resources are asked and read, and
`server` how the shared MCP server of `connectors/serving.py` serves it.
"""
