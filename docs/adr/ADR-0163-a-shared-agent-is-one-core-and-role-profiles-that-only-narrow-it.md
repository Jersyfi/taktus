# ADR-0163 — A shared agent is one core and role profiles that only narrow it

**Status:** accepted · extends ADR-0131 (a person's agent on the MCP surface), ADR-0134 (evaluation cases) and ADR-0162 (know-how handed to a step) · issue #647, UC-8.11

## Context

Several departments often need the same agent: an inbox prioritiser, a knowledge assistant, an
onboarding helper. UC-8.11 asks for one agent with role profiles instead of a copy per
department. The core is maintained once. A profile sets only what varies by role. A change of
the core reaches every role, and it goes into production only when every profile's evaluation
passes.

An "agent" in the repository so far was an access surface: a person's own agent reaching
Taktus over MCP with the rights of their role (ADR-0131). Rights per role exist as
`RoleRights`, and the roles of a tenant's structure are read through `RoleStructure`. Nothing
described an agent that Taktus provides and several roles share.

Three words are used below. A **core** is one version of what every role shares. A **profile**
is one version of what one role of the tenant uses of the core. **Grants** are what may be
used: knowledge sources, connectors, tools, output formats and an approval limit.

## Decision

### 1. The core

The catalogue keeps one record per core version, `AgentCore`, named `<agent>@<version>`. It
holds the agent's purpose and instructions, its **flow** — the process that runs when the agent
is called — the model purpose it asks, its autonomy level, and its grants: the most any role
may use. A core version never changes. A new version is proposed and **held**. It becomes
**active** when nothing holds it (§4), and the active version before it is superseded.

### 2. The profile, which only narrows

A profile is `<agent>:<role>@<version>`, versioned apart from the core. It sets the role's
grants, its vocabulary and its tone. Each of its grants lies within the active core's: each
list is a subset, and its approval limit is at most the core's. A profile that would grant more
is refused, and `agent.profile_refused` records it with outcome `widens`. A new version of a
role's profile replaces the one before it, which is kept inactive. A profile is keyed by a
role. No profile names a person (principle 14).

### 3. The profile is resolved from the caller's role

A caller holds roles in the tenant's structure (UC-1.4). The caller may choose one, and a role
they do not hold is refused. Without a choice:

- one held role with a profile: that profile (`only`);
- several: the profile with the **fewest rights** (`fewest_rights`). A profile whose grants
  are a strict subset of another's has fewer. Where neither is a subset, the one with fewer
  grants has fewer, then the one with the lower approval limit, then the role first in order;
- none: the call is refused. The core is never served unnarrowed.

### 4. A core change is held until every profile's evaluation passes

A profile's evaluation is an ADR-0134 evaluation of purpose `profile` on the flow's cases. Both
sides run the flow's active version as rehearsals and serve the profile. The active side runs
under the active core, the proposed side under the held core. The verdict is the rule of a
change: `passed`, `regressed` or `incomplete`. The verdict is recorded on the held core, by
profile. A held core becomes active only when every active profile's verdict on it is `passed`
and every active profile still lies within its grants. Otherwise it stays held for every role,
and `agent.core_held` records it once every profile has a verdict.

### 5. A call runs the flow as the caller, serving the profile

A call resolves the profile and starts the core's flow, as the caller, through the one path
every run takes. The run carries the profile (`Run.profile`). Its steps on a model or a worker
receive the core's instructions and the profile's tone, vocabulary, formats and sources in
their brief, in the same place a skill is handed over (ADR-0162 §5). A flow whose steps need a
tool or connector the profile does not grant is refused before it starts. `agent.called`
records the call with the profile in `refs.agent_id`, the run, the caller as actor, and how the
profile was found as outcome. The run acts as the caller, so it uses the caller's own
credentials, as any run does (UC-8.7).

### 6. Use and cost by profile, never by person

Use and cost are read by profile: the calls `agent.called` records and what their runs cost.
No figure is computed per caller (principle 14, UC-8.5).

### 7. The diagram

`taktusctl agent diagram` prints a Mermaid flowchart. The core is drawn with its flow, level and
grants. Each active profile is drawn with only what differs from the core: what it leaves out,
its approval limit, its tone and its vocabulary (UC-4.2).

### 8. Method and exactness

| Part | Method | Exactness | Reason | Rejected |
|---|---|---|---|---|
| the narrowing check | `rule` | `exact` | set inclusion and a comparison of amounts | `llm` — a right granted by a model's reading |
| the resolution | `rule` | `exact` | the same roles give the same profile every time | `llm` — the least privilege must not vary |
| holding a core | `rule` | `exact` | recorded verdicts per profile and the grants (ADR-0023) | `statistics` — one verdict per profile is the evidence UC-8.11 names |

## Alternatives

- **A copy of the agent per department.** Rejected by UC-8.11: a change would be made once per
  copy, and the copies drift apart.
- **The profile as a process version of its own.** Rejected: a change of the core would need a
  new version of every process, and the core would not be maintained once.
- **Serving the core when no role has a profile.** Rejected: least privilege (UC-7.3).
- **Choosing among several roles by the order they were granted in.** Rejected: who granted
  first is no measure of rights.

## Consequences

- The catalogue gains `AgentCore`, `RoleProfile`, `Grants`, the rules in
  `domain/service/agents.py` and the application service `AgentCatalog`.
- The process component gains purpose `profile` on `Evaluation`.
- The run component gains `Run.profile` and `StartRun.profile`, read through the port
  `Guidance`.
- The composition root gains `SharedAgents` (`composition/agents.py`) and `taktusctl agent`.
- `LedgerRefs.agent_id`, and the kinds `agent.core_proposed`, `agent.core_held`,
  `agent.core_activated`, `agent.profile_set`, `agent.profile_refused` and `agent.called`.
- Migration 0090 adds the tables `agent_core` and `role_profile` and the column `run.profile`.

## Where this promise ends

A profile narrows what the catalogue records and what the flow's steps declare. A tool a worker
reaches by itself, inside the frame of its assignment, is bounded by that frame, not by the
profile. A profile's sources and formats reach a step as words in its brief. Nothing checks
that a step's answer keeps to them.

A profile's evaluation is only as good as the flow's evaluation cases. A flow without cases
gives no verdict, and a core change of such an agent is held until a person records one. One
verdict per profile is required. It is the verdict of one evaluation, and a model's answers
vary between evaluations.

The fewest rights are decided by the order of §3. Two profiles whose grants are not comparable
are ordered by counting grants, and a count does not weigh what a grant allows. A caller with
several roles who wants another profile must choose it.

Use and cost are counted from the ledger's `agent.called` entries and their runs. The value an
agent brings to a role is not measured here (UC-9.3). The agent is called through
`taktusctl agent call` and the composition root. No HTTP or MCP route calls a shared agent yet.
