# ADR-0292 — An agent is drafted in the plan dialogue, and registered when its plan is commissioned

**Status:** accepted · extends ADR-0237 and ADR-0238 (the plan dialogue and its two modes),
ADR-0163 and ADR-0287 (a shared agent's core and its description), ADR-0246 (shares) · UC-8.7,
UC-1.2

## Context

UC-8.7 asks that an agent be built from a description worked out in dialogue (UC-1.2), with all
six parts — its role, its instructions, the knowledge it reads, the tools it may use, the model
purpose it asks and its autonomy level — and an autonomy level with its reason (ADR-0026). The
agent is shared only after a person accepted it.

The plan dialogue exists (ADR-0237, ADR-0238). The catalogue registers an agent's core
(ADR-0163), refuses a grant named after a product (ADR-0287), and shares an agent only by a
person's act and only with an active core (ADR-0246). Nothing joined the two: an agent was
proposed from a YAML file by `taktusctl agent core`, never worked out in the dialogue.

## Decision

### 1. An agent draft is a plan draft with an agent part

A plan draft may carry an **agent part**: the agent's name and version, its instructions, the
model purpose it asks, its tools, its knowledge sources, and optionally its connectors, its
output formats and its approval limit. The other parts are the plan draft's own: the goal is the
agent's role, the chosen process version is its flow, and the autonomy level and its reason are
the agent's. One record holds the agent as it is worked out; there is no second one. A draft is
opened as an agent draft, or becomes one when the expert mode sets its agent part.

A draft with an agent part lacks, besides the four parts of ADR-0237, each of these not yet
stated: the agent's name, its instructions, the model purpose it asks, the tools it may use, the
knowledge it reads, and the process it runs. The process it runs is the process of the chosen
version; steps described by hand name none. An empty list of tools or of sources is stated; only
one never given is lacking.

### 2. The guided mode asks for what the agent lacks

After the steps, the guided mode asks for each part the agent lacks, in the order of §1, before
the date it is due. When a process version is chosen for an agent draft whose tools were never
stated, its tools are the tool actions the flow uses, and nothing more (ADR-0261 §4). That is
Taktus building the agent from what it knows; a person refines it in either mode. Every agent
setting is shown with its value and why, like every other setting (ADR-0238 §3). Whether the
draft works out an agent is a third setting the guided mode never asks, beside the two of
ADR-0238 §3: it is chosen when the draft is opened, and shown on every draft.

### 3. Commissioning an agent draft registers the agent through the catalogue

Commissioning an agent draft is the plan's commissioning (ADR-0237 §3), followed by the
catalogue's registration of the core. Before either writes, it is refused, naming what it
finds, when:

- the draft lacks a part, or a step cannot be estimated (ADR-0237 §3);
- the tools do not grant every tool action the flow uses (ADR-0261 §4);
- a tool, source or connector is named after a product (ADR-0287 §2);
- the core version already exists (ADR-0163).

Then the plan is commissioned, recording `plan.commissioned`. The core is proposed through
`AgentCatalog.propose_core`, by the identity that commissioned, recording `agent.core_proposed`
with the commissioned plan in `refs.plan_id`. The core keeps the autonomy reason, and the
description states it. A core proposed through the dialogue passes every check one proposed
from a file passes; the dialogue holds no check of its own in their place.

The plain commissioning of an agent draft without the catalogue is refused. An agent draft never
becomes a plan alone.

### 4. Sharing stays its own act

Commissioning is the person's acceptance of the agent. It does not share it. Sharing is
`CatalogueShares.share`, by a person, with an active core (ADR-0246). Before commissioning the
agent has no core, so a share is refused as `not_accepted`.

## Alternatives

- **A dialogue of the catalogue's own for agents.** It would be a second dialogue with its own
  questions, modes and refusals. Rejected: UC-8.7 rests on UC-1.2's one dialogue.
- **A new `results_in` value, `agent`, in the shared kernel's plan.** It would change a
  published contract for what only the dialogue needs. The agent part is the `command`
  component's own record, kept in the draft's document.
- **A new ledger kind, `agent.drafted`.** `agent.core_proposed` already names the core and the
  actor; `refs.plan_id` joins it to the commissioned plan. No kind is added.

## Consequences

- `command/domain/model/planning.py`: `AgentPart`, `PlanDraft.agent`, its parts in `missing`.
- `command/domain/service/guided.py`: the agent's questions and settings.
- `command/application/service/plan_dialogue.py`: `agent` revisable.
- `catalog/domain/model/agent.py`: `AgentCore.autonomy_reason`; `catalog/application/service/
  agents.py`: `check_named`, and `plan_id` and `autonomy_reason` on `propose_core`.
- `composition/agent_drafting.py`: the commissioning of an agent draft;
  `composition/planning.py` routes an agent draft to it; `composition/workspace.py` and the
  daemon hand it the catalogue.
- `adapters/driving/rest/planning.py`: `POST /plans` takes `agent`, and the commissioning answers
  with the agent it registered.

## Where this promise ends

- The agent's instructions are taken as the person states them. Whether they are good is the
  person's (UC-8.7 §3), and Taktus does not write them.
- The plan draft and its commissioning record the agent's core only. A role profile, which a
  call of a shared agent needs (ADR-0163), is set by its own act afterwards. So is a share.
- The checks of §3 run before anything is written, but the plan and the core are two units of
  work. A core version taken by another act between the check and the registration leaves the
  plan commissioned and the agent unregistered. The refusal says so, and a new version of the
  draft is commissioned again.
- A release before this decision reads no agent part. It cannot read a draft that carries one.
