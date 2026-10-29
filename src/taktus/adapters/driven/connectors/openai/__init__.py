"""The model costs connector: the connector contract v1 over the OpenAI organization costs API.

The capability `models.costs`: what an organisation spent at a model provider per day, by line
item or by project, as the provider's billing reports it. This directory, its README and
configuration are the only places that name the product. Everywhere else it is the capability
(CLAUDE.md §6, ADR-0150).

Run it: `python -m taktus.adapters.driven.connectors.openai`. The modules: `declaration` is what
it declares, `operations` how the costs are asked and read, and `server` how the shared MCP
server of `connectors/serving.py` serves it.
"""
