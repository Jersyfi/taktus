"""The model costs connector over the Anthropic Admin API's cost report: the connector contract
v1 for the capability `models.costs`.

What an organisation spent at the model provider per day, by description (model and token type)
or by workspace, as the provider's billing reports it, in the shape the other `models.costs`
connector answers. And the capability `models.catalogue`: which models a key may use, from the
provider's models list. This directory, its README and configuration are the only places that name
the product. Everywhere else it is the capability (CLAUDE.md §6, ADR-0150).

Run it: `python -m taktus_connectors.anthropic`. The modules: `declaration` is
what it declares, `operations` how the costs and the catalogue are asked and read, and `server`
how the shared MCP server of `connectors/serving.py` serves it.
"""
