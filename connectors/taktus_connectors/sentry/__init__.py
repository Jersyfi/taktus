"""The error tracking connector: the connector contract v1 over the Sentry API.

The capability `errors.issues`: the issues an error tracker grouped from its events, listed by
a query over a period, or read one at a time. This directory, its README and configuration are
the only places that name the product. Everywhere else it is the capability (CLAUDE.md §6,
ADR-0150).

Run it: `python -m taktus_connectors.sentry --organization <slug>`. The
modules: `declaration` is what it declares, `operations` how the issues are asked and read, and
`server` how the shared MCP server of `connectors/serving.py` serves it.
"""
