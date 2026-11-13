# ADR-0311 — A step may name the configured connector that serves it

**Status:** accepted · extends ADR-0024 (connector steps) and ADR-0281 (residency of a
connector) · serves UC-03 B-3.10 · issue #401

## Context

A run resolves a capability to the first configured connector whose declaration lists it. One
instance therefore reaches one system per capability. B-3.10 sorts what is said about the
product on a social network *and* in forums. Both connectors serve `mentions.search` in one
shape. Until now a business that watched both places needed an instance per place. The
blueprint's README named this as the gap.

The configuration already gives every connector an identifier of its own, such as
`connector.forum`. The ledger records that identifier, never a product (CLAUDE.md §6).

## Decision

1. **A connector step may carry `connector`.** Its value is the identifier under which the
   instance's configuration names a connector. It is never a product name. A bundle usually
   takes it from an input, `{ $input: source }`, so that each tenant names its own
   configuration.
2. **The named member serves the step.** The connector pool answers `named(identifier,
   capability)`: the member with that identifier, where its declaration lists the capability.
   No other member stands in for it.
3. **Without `connector` nothing changes.** The first configured connector for the capability
   serves, as before.
4. **Every reading of the step follows the name.** These all read the named member:
   - the call itself;
   - its estimate;
   - whether its operation is outward;
   - the message frame;
   - the residency check;
   - the list of what serves a step.
5. **A rehearsal answers by capability.** Its pool is the recording, which knows no identifiers.
6. **B-3.10, version 3,** reads `source` and, where given, `second`, each through a search step
   that names it. The model sorts the posts of both.

## Alternatives

- **A second capability per place, such as `mentions.forum`.** A process would then name the
  kind of system it reads. That breaks "a process runs on either source unchanged".
- **An instance per source.** This was the state before. It doubles the operation of the
  instance for one process.
- **A connector name in the core's code.** Forbidden by the adapter obligation. The name is
  configuration and reaches the step as data.

## Consequences

- `ConnectorRule` gains `connector`.
- The run's ports gain the protocol `NamedConnectors`, and `StaticConnectorPool` implements it.
- The run engine, `composition.pools` and `composition.residency` resolve a named step through it.

## Where this promise ends

- **A name the configuration does not carry is not served.** The engine cannot read what the
  step would do. It holds the step for a person, or fails it when the step runs. It never falls
  back to another member.
- **A rehearsal does not check the name.** It answers from the recording by capability.
- **The credential is named per call, not per connector.** Two connectors of one capability
  read their key under the same parameter. Each runs as its own process with its own file. Two
  connectors served in one process share the value.
- **The bundle cannot know the identifiers.** The tenant gives them as inputs, or its version
  fixes them.
