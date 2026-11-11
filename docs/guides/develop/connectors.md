A **connector** lets Taktus read and write in another system, such as a ticket system or a chat,
and turns that system's events into requests. It is an MCP server: a program that speaks the
Model Context Protocol, an open protocol for tools. It can be written in any language and run
anywhere Taktus reaches it.

## What you build

1. **The declaration**: the capabilities the connector serves, and for each operation its
   effect, its idempotency and its demand. The connector serves it as an MCP resource.
2. **The operations**: one MCP tool per declared operation.
3. **A fake of the target system**: a small server that answers as the real one does, so that the
   connector is tested without a network and without an account.
4. **A scenario**: the inputs the conformance suite calls your operations with.

The connectors this repository ships live under `connectors/taktus_connectors/`, one directory
each. `depsdev/` is a small one to copy: `declaration.py`, `operations.py`, `server.py`,
`scenario.json` and a README. Its fake is `tests/fakes/package_index_service.py`.

An instance reaches a connector through an entry of `TAKTUS_CONNECTORS`, which maps a capability
to the connector's MCP address, such as `packages.licences=http://packages-connector:9171/mcp`.
The credentials it needs are files the operator provides (*Configuring*, in the administration
guide).

The rest of this page is the contract's own text: the MCP binding, the declaration, idempotency,
and how the conformance suite checks a connector.
