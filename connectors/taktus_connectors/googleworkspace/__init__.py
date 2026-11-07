"""The workspace audit connector: the connector contract v1 over the Google Workspace Admin
SDK Reports API.

The capability `audit.events`: the administrators' actions in a workspace, read with the fields
a rule over actions needs. This directory, its README and configuration are the only places
that name the product. Everywhere else it is the capability (CLAUDE.md §6, ADR-0209).

Run it: `python -m taktus_connectors.googleworkspace --subject <administrator>`. The modules:
`declaration` is what it declares, `operations` how the activities are asked and read, and
`server` how the shared MCP server of `connectors/serving.py` serves it.
"""
