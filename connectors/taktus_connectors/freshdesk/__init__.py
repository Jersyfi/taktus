"""The second helpdesk connector: the connector contract v1 over the Freshdesk API v2.

The capability `helpdesk.tickets`, in the shapes the other helpdesk connector answers
(ADR-0205). This directory, its README and configuration are the only places that name the
product. Everywhere else it is the capability (CLAUDE.md §6, ADR-0150).

Run it: `python -m taktus_connectors.freshdesk --target https://<domain>.freshdesk.com`. The
modules: `declaration` is what it declares, `operations` how the tickets are asked and written,
and `server` how the shared MCP server of `connectors/serving.py` serves it.
"""
