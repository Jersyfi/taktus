# ADR-0287 — An agent is described from its version, and names capabilities only

**Status:** accepted · extends ADR-0163 (a shared agent's core and role profiles), ADR-0246 and
ADR-0247 (shares and the caller's credential) · UC-8.7 · DEC-0228

## Context

UC-8.7 asks that no agent be a black box. Every agent shows what it does as a diagram and as a
description in plain language. The description names what the agent does, what it reads, which
tools it may use, and what it must not do. Both are generated from the agent's version and never
edited apart from it. Tools and knowledge sources are named by capability, never by product
(ADR-0003).

The diagram exists (ADR-0163, `agents.diagram`). A description does not. Nothing checked how a
core or a profile names its grants: a tool `github.issues.read` was accepted as readily as
`issues.read`.

## Decision

### 1. The description is generated from the version

`agents.describe(core, profiles)` writes Markdown in five sections:

- **What it does**: the core's purpose, the process it runs, the model purpose it asks, and what
  its autonomy level means for acting on its own.
- **What it reads**: its knowledge sources and connectors.
- **Which tools it may use**: its tools, and the output formats it answers in.
- **What it must not do**: use a tool, a source or a connector not named; act above its level,
  whoever calls it; approve an amount above its approval limit, or any amount where it has none;
  act with its author's credential (ADR-0247).
- **By role**: what each active profile leaves out of the core, and its approval limit.

It is a rule: the same core and profiles give the same text. Nothing stores it.
`taktusctl agent describe <agent> [--version <v>]` prints it, for the active core or a named
one.

### 2. Grants name capabilities, never products

A core and a profile are refused, with the outcome `product` and every finding, where:

- a tool is not a capability: lowercase dotted segments, at least two (`Capability.json`);
- a segment of a tool, a source or a connector is a product's name.

The product names are the composition's to give. They are the names of the connectors the
release ships that are not the first segment of any capability those connectors offer
(`composition/shipped.py`, `product_names`). A connector named after what it does, such as
`accounting`, is therefore no product. The catalog component holds no product name itself.

## Alternatives

- **A description written by the agent's author.** It would drift from what the agent may do.
  Rejected: UC-8.7 asks for one generated from the version.
- **A description written by a language model.** It could be wrong, and could differ between two
  readings. Rejected: a rule over the version says exactly what is granted.
- **A fixed list of product names in the catalog.** It would put product names in the core.
  Rejected (ADR-0003).

## Consequences

- `catalog/domain/service/agents.py`: `describe`, `named_by_product`.
- `catalog/application/service/agents.py`: `AgentCatalog.describe`, and the refusal on
  `propose_core` and `set_profile`.
- `composition/shipped.py`: `product_names`, handed to the catalog by both wirings.
- `adapters/driving/cli/agent_command.py`: `taktusctl agent describe`.

## Where this promise ends

- The description says what the agent is granted. Whether its instructions are good is the
  author's (UC-8.7 §3 leaves the content to the person).
- A product the release does not ship as a connector is not known by name. A grant naming it is
  accepted. Knowledge sources are named by the organisation; only a source that names a shipped
  product is refused.
- A core stored before this decision is not checked again. It is checked when a new version is
  proposed.
- Drafting an agent from a description worked out in dialogue rests on the plan dialogue of
  UC-1.2. It is not part of this decision.
