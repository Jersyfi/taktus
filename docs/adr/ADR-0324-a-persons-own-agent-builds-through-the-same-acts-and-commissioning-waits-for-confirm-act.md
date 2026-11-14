# ADR-0324 — A person's own agent builds through the same acts, and commissioning waits for `confirm_act`

**Status:** accepted · amends ADR-0131 (§3, §5 and where its promise ends) · extends ADR-0008, ADR-0237, ADR-0091 · UC-1.11, DEC-0239

## Context

ADR-0131 gave a person's own agent a surface over the Model Context Protocol (MCP), at
`<prefix>/mcp`. The agent can read, start a process, answer a decision request and take over a
step. It cannot build: UC-1.11 §3 kept changing a process away from it, and ADR-0131 ended its
promise with "changing a process … not offered".

DEC-0239 changed that requirement. A person's own agent may now plan a process, ask Taktus to
change or describe one, rehearse and commission what Taktus proposes, and roll a process back.
It does so through the same services, checks and read-back as the web app. Steering a run and
the emergency stop stay where they are.

Two things must not get weaker on the way. First, the agent acts as the person, and only within
the rights of their roles (ADR-0131 §3). Second, an act that changes a process takes effect only
once the person confirms how it was read (ADR-0008). An agent may misread an instruction, or
follow one planted in what it read.

## Decision

### 1. One closed list of acts, shared with Taktus's own conversation

The acts of building are a closed list in the command component (`ACTS`,
`components/command/domain/model/conversation.py`): `open_plan`, `answer_plan`, `set_plan`,
`commission_plan`, `ask_change`, `ask_description`, `rehearse_proposal`, `commission_proposal`,
`discard_proposal`, `rollback_process` and `start_process`. Each names its arguments and their
kinds. A rule checks every call against the list: an unknown act, an argument the act does not
declare, a missing one or one of the wrong kind is refused, naming it. Taktus's own
conversation proposes acts from the same list (ADR-0325).

The composition root does each act (`composition/building.py`) through the service the web app
uses: the plan dialogue (ADR-0237), the request path for a change or a description (ADR-0091 §2,
ADR-0251), the acts on a proposal (ADR-0091 §3 to §5), and the one start command (ADR-0131 §5).
Each acts as the person. Registration's own checks apply as they do on the web, among them the
rights of ADR-0257.

### 2. Two new rights, granted to a role

| Right | What it permits on the MCP surface |
|---|---|
| `agent.plan` | open, answer, set and commission a plan draft of the person's own |
| `agent.change` | ask for a change or a description of a process; rehearse, commission and discard a proposal; roll a process back |

They join the rights of ADR-0131 §3 and follow its rules. A right is granted to a role, never
to a person, and granting and withdrawing it are ledger entries. A tool is listed only where a
role of the person holds its right. A call without it is refused, naming the right, and
nothing changes.

### 3. Commissioning and a rollback are read back, and only `confirm_act` does them

Three acts change a process or start work at once: `commission_plan`, `commission_proposal` and
`rollback_process`. Called over MCP, none takes effect. The act is read back by rule — "Commission
proposal p_1: version 2 becomes the active version of invoices" — and kept in the person's
conversation (ADR-0325 §1) under an identifier. The answer names that identifier.

`confirm_act` with `confirmed: true` does the act as the person; with `false` it records that
nothing was done. Either is a ledger entry, `conversation.act_confirmed` or
`conversation.act_declined`, with the person as actor. The right the act needs is checked again
at the confirmation: a right withdrawn in between refuses it. `confirm_act` is listed to whoever
holds `agent.plan` or `agent.change`. An act already settled is refused.

The other acts change a draft, start a run that proposes, or discard a proposal. None changes a
process, and each takes effect at once, as on the web.

### 4. The new tools

| Tool | Right | What it does |
|---|---|---|
| `list_plans`, `get_plan` | — | the person's plan drafts, and one with the question it asks next |
| `list_proposals`, `get_proposal` | — | the proposals for a process the person may see, and one with its difference |
| `open_plan`, `answer_plan`, `set_plan` | `agent.plan` | a plan draft opened, answered, set; each a new version of it |
| `commission_plan` | `agent.plan` | read back; done by `confirm_act` |
| `ask_change` | `agent.change` | a run of the change process proposes a changed version (S-07) |
| `ask_description` | `agent.change` | a run of the describe process proposes a new process (S-08) |
| `rehearse_proposal`, `discard_proposal` | `agent.change` | as on the web |
| `commission_proposal`, `rollback_process` | `agent.change` | read back; done by `confirm_act` |
| `confirm_act` | the act's | the read-back confirmed or rejected |

Every act on a process asks the visibility predicate first. A process the person may not see is
answered as one that does not exist. Every call is in the ledger as `agent.<tool>`, as ADR-0131
§6 says.

## Alternatives

- **Confirmation as an argument (`confirmed: true` on the first call).** Rejected: an agent
  would set it on the first call, and nothing would be read back.
- **One right for everything that builds.** Rejected: planning one's own work and changing a
  process the tenant runs are different reaches; an administrator grants them apart.
- **Tools of their own beside the web's services.** Rejected: two paths to the same act drift
  apart, and the web's checks would have to be written twice.

## Consequences

- The identity component knows the rights `agent.plan` and `agent.change`. No migration is
  needed: the rights per role are stored as names (migration `0066`).
- The surface serves 27 tools. The act inventory of ADR-0279 is untouched: it lists the
  administrative acts, and none of these is one.
- The README of the surface and the guide `docs/guides/use/talking.md` describe the tools as
  built.

## Where this promise ends

The read-back covers the three acts of §3; the others take effect at once, as on the web. The
read-back is said by rule from the act and its arguments, and names what it looks up — a
proposal's version, a draft's goal — as they stand when it is said; what changes between the
read-back and the confirmation is not read back again. An act waits in the person's
conversation until it is confirmed or rejected; it does not expire. Steering a run and the
emergency stop are still not offered (UC-1.11 §3). The rights bound what an agent can do, not
whether it does it well: an agent that holds `agent.change` and is told to confirm will
commission a proposal its person never read. Whether the person read a read-back is not
something Taktus can tell.
