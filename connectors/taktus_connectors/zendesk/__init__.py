"""The helpdesk connector: the connector contract v1 over the Zendesk Support API and its Help
Center API.

The capabilities `helpdesk.tickets` and `helpcentre.articles` (ADR-0205). This directory, its
README and configuration are the only places that name the product. Everywhere else it is the
capability (CLAUDE.md §6, ADR-0150).

Run it: `python -m taktus_connectors.zendesk --target https://<subdomain>.zendesk.com`. The
modules: `declaration` is what it declares, `operations` how the tickets and articles are asked
and written, and `server` how the shared MCP server of `connectors/serving.py` serves it.
"""
