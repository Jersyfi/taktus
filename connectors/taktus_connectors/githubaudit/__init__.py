"""The audit connector: the connector contract v1 over the GitHub organisation audit log.

The capability `audit.events`: the privileged actions of an organisation, read with the fields a
rule over actions needs. This directory, its README and configuration are the only places that
name the product. Everywhere else it is the capability (CLAUDE.md §6, ADR-0209).

Run it: `python -m taktus_connectors.githubaudit --organization <login>`. The modules:
`declaration` is what it declares, `operations` how the audit log is asked and read, and
`server` how the shared MCP server of `connectors/serving.py` serves it.
"""
