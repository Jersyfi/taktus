"""The reference connector: the connector contract v1 against a repository hosting service.

Capabilities `repository.issues`, `repository.pullrequests`, `repository.pipelines` and
`repository.comments` as actions, and webhook intake normalised into commands. Everywhere else in
this repository it is named by those capabilities; the product it talks to appears only here,
in README.md and in configuration.

Run it: `python -m taktus.adapters.driven.connectors.github --port 9100 --repository owner/name`.
The modules: `declaration` is what it declares, `api` how it talks to the service, `operations`
what each operation does — including how a repeat is recognised — `intake` how an event becomes
a command, `faults` what it can be made to do wrong, and `server` the MCP server that ties them.
"""
