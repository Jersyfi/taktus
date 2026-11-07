"""The log store connector: the connector contract v1 over the Grafana Loki HTTP API.

The capability `logs.query`: the log lines a LogQL query selects within a window, newest
first. This directory, its README and configuration are the only places that name the
product. Everywhere else it is the capability (CLAUDE.md §6, ADR-0150).

Run it: `python -m taktus_connectors.loki --target <address>`. The modules: `declaration` is
what it declares, `operations` how the lines are asked and read, and `server` how the shared
MCP server of `connectors/serving.py` serves it.
"""
