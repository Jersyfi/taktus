"""The chat connector: the connector contract v1 against a chat service.

The capability `chat.threads` as actions — read a thread, post into a conversation or a thread —
and event intake normalised into commands on the channel `channel.chat`. Everywhere else in this
repository it is named by that capability and that channel; the product it talks to appears only
here, in README.md and in configuration.

Run it: `python -m taktus.adapters.driven.connectors.slack --port 9101`. The modules:
`declaration` is what it declares, `api` how it talks to the service, `operations` what each
operation does — including how a repeat is recognised — `intake` how an event becomes a
command, `faults` what it can be made to do wrong, and `server` the MCP server that ties them.
"""
