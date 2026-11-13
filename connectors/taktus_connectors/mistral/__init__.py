"""The model catalogue connector over Mistral AI's models list: the connector contract v1 for
the capability `models.catalogue`.

Which models a key may use, and which of them the provider has set a deprecation for, in the
shape the other `models.catalogue` connectors answer (ADR-0204). The provider publishes no API
for an organisation's costs or usage, so this connector serves no `models.costs`. This
directory, its README and configuration are the only places that name the product. Everywhere
else it is the capability (CLAUDE.md §6, ADR-0150).

Run it: `python -m taktus_connectors.mistral`. The modules: `declaration` is what it declares,
`operations` how the catalogue is asked and read, and `server` how the shared MCP server of
`connectors/serving.py` serves it.
"""
