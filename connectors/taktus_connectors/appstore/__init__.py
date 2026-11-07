"""The signing credentials connector: the connector contract v1 over the App Store Connect API.

The capability `expiry.credentials`: when a team's signing certificates and provisioning
profiles expire, and never their content. This directory, its README and configuration are
the only places that name the product. Everywhere else it is the capability (CLAUDE.md §6).

Run it: `python -m taktus_connectors.appstore`. The modules: `declaration` is what it
declares, `token` how a request is authorised, `operations` how the certificates and profiles
are listed, and `server` how the shared MCP server of `connectors/serving.py` serves it.
"""
