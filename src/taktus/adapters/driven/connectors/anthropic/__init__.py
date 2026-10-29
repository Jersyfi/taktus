"""The model costs connector over the Anthropic Admin API's cost report: the connector contract
v1 for the capability `models.costs`.

What an organisation spent at the model provider per day, by description (model and token type)
or by workspace, as the provider's billing reports it, in the shape the other `models.costs`
connector answers. This directory, its README and configuration are the only places that name
the product. Everywhere else it is the capability (CLAUDE.md §6, ADR-0150).

Run it: `python -m taktus.adapters.driven.connectors.anthropic`. The modules: `declaration` is
what it declares, `operations` how the costs are asked and read, and `server` how the shared MCP
server of `connectors/serving.py` serves it.
"""
