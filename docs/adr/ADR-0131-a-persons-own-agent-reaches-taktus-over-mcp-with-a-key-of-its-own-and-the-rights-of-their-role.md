# ADR-0131 — A person's own agent reaches Taktus over MCP, with a key of its own and the rights of their role

**Status:** accepted · extends ADR-0040 (identity), ADR-0008 (the decision request), ADR-0119 (the account key on the surface) and ADR-0128 (taking over a running step) · issue #406, DEC-0195 W5, UC-1.11

## Context

A person increasingly works through an agent of their own: a coding agent, or a chat
assistant. Such an agent is offered tools over the Model Context Protocol (MCP), an open
standard. Taktus already speaks MCP towards its connectors (ADR-0024): there Taktus is the
client. DEC-0195 adopted W5: Taktus becomes an MCP server too, so that a person's agent can
start a process, read how its runs stand, answer a decision request and take over a step.

Three things already exist that this surface must not weaken:

- **Who acts.** Every act on the control plane's surface acts as one identity. The identity is
  proved by its account key, or by the web app's session that was exchanged for it (ADR-0119).
- **What a reader sees.** One predicate decides which runs and processes a reader may see. Every
  read and the stream of changes ask it (ADR-0055 §5, UC-6.4).
- **A free-text answer is read back.** An answer to a decision request takes effect only once
  the person confirms how it was read (ADR-0008).

An agent is not the person. It may misread an instruction, or follow one planted in what it
read. The owner's condition in W5 is therefore that an agent can only read until a right to act
was granted. UC-7.3 requires every right to be granted to a role, never to a named person.

If the agent held the person's account key, a right on the MCP surface would bind nothing. The
same key opens the HTTP surface, which knows no such right. The agent could act there instead.

## Decision

### 1. The `api` role serves MCP at `<prefix>/mcp`

The process that serves the HTTP surface also serves MCP, on the same port and under the same
prefix (ADR-0063). The binding is MCP's streamable HTTP transport. It is stateless: every HTTP
request stands alone and is answered as JSON. No session is kept between requests, so any
replica can answer any request.

The surface offers tools only. It offers no resources and no prompts. It forwards nothing to
another MCP server.

### 2. An agent proves the person with an agent key, which opens nothing else

A person's agent holds an **agent key** of its own. It is the key of one identity, with the
prefix `tkg_`. Only its digest is kept, as for the account key. A new agent key replaces the
one before. The ledger records `identity.agent_key_issued`.

- The person creates it with their account key: `POST /identity/agent-key`. An administrator
  can issue one as well: `taktusctl identity agent-key`.
- The MCP surface accepts only an agent key, in `Authorization: Bearer`. An account key, a
  session cookie and no credential at all are refused with `401` before any message is read.
- The HTTP surface never accepts an agent key. An agent therefore has no way round the rights
  of §3.

Every request is authenticated anew. A key replaced since the last request stops working at the
next one.

### 3. To act, a role the person holds needs the right

Reading needs no right beyond the key. Every tool that changes something needs one of three
rights, each granted to a role:

| Right | What it permits |
|---|---|
| `agent.start` | start a process's active version |
| `agent.answer` | answer a decision request addressed to the person, and confirm its reading |
| `agent.take-over` | take over a running step, and hand its result back |

The identity component keeps, per tenant, which rights each role holds. An administrator grants
and withdraws them: `taktusctl identity grant` and `taktusctl identity withdraw`. The ledger
records `identity.right_granted` and `identity.right_withdrawn`, with the administrator as actor.
No right is granted to a named person; there is no record that could hold one.

The rights an identity holds are the union of its roles' rights, read at the moment of each
call. A role taken from the person takes its rights with it at the next call.

### 4. A client is offered what the identity may use, and served no more

- The tools a client lists are the read tools, and each write tool whose right the identity
  holds.
- A write tool called without its right is refused. The refusal names the right, and nothing
  changes. Listing is a courtesy: the check is made on every call.
- Every read asks the visibility predicate, as the HTTP surface does. A run the reader may not
  see is answered as one that does not exist.
- Starting a process asks the predicate for the process too.
- A decision request is answered only by an identity holding its deciding role, as on the HTTP
  surface (ADR-0042).

### 5. The tools

| Tool | Right | What it does |
|---|---|---|
| `list_processes` | — | the processes with an active version the reader may see, with their inputs |
| `start_process` | `agent.start` | starts the active version with the given inputs; the run acts as the person |
| `list_runs`, `get_run` | — | the runs the reader may see, and one with its steps |
| `list_decisions`, `get_decision` | — | the decision requests addressed to the person |
| `answer_decision` | `agent.answer` | an option or free text; the reading comes back, and nothing takes effect |
| `confirm_decision` | `agent.answer` | the reading confirmed takes effect; rejected, the request is open again |
| `take_over_step` | `agent.take-over` | asks the take-over of ADR-0128 §1 |
| `show_takeover` | — | the state the step was taken over in (ADR-0128 §3) |
| `hand_back` | `agent.take-over` | the result handed back as a `human` step (ADR-0128 §5) |

The tools call the same application services as the HTTP surface. A process started here goes
the one path every channel takes: a command on the channel `channel.agent`, a commissioned plan,
a run submitted to the queue.

`answer_decision` never takes effect alone, even for an option named by its letter. The reading
is reflected back, and the agent must call `confirm_decision`. An agent that is told by its
person to confirm does so as the person, under the same right.

### 6. Every call is in the ledger, with the identity as its actor

Every call of a tool, a read included, records an entry of kind `agent.<tool>` in the ledger,
`agent.start_process` for instance. Its actor is the identity; its outcome is `served`,
`refused` or `failed`; it names the run where the call names one. Its content digest is the digest of the tool's name and its arguments. The arguments
themselves are not kept: the ledger stays content-free.

A call that acts records, in addition, what the act itself records — `run.created`,
`decision.answered`, `step.takeover_asked` and so on — with the same actor.

No measure is computed from these entries per person (principle 14). The entries are the audit
of what an agent did as whom.

## Alternatives

- **The account key on the MCP surface too.** Rejected: an agent holding it acts on the HTTP
  surface without any right (Context).
- **Rights granted to a key.** Rejected: UC-7.3 grants every right to a role, never to a named
  person. A key belongs to one person.
- **An identity of the agent's own** (as ADR-0033 gives Taktus towards a service). Rejected for
  now: the agent acts for the person, and its acts must be theirs — a decision addressed to them
  is answered by them. An identity of its own would need its own roles and its own deciders.
- **A stateful MCP session.** Rejected: a session lives in one replica's memory and dies with
  it. Every request authenticates anyway.
- **Only acting tools listed, no check on call.** Rejected: a client may call a tool it was not
  offered. The listing shows; the call decides.

## Consequences

- The identity gains the digest of its agent key, and the identity component a record of the
  rights per role (migration `0066`).
- `taktusctl identity` gains `agent-key`, `grant`, `withdraw` and `rights`. The HTTP surface
  gains `POST /identity/agent-key`.
- The take-over of ADR-0128 §7 is offered on the MCP surface.
- The README describes the surface as built.

## Where this promise ends

The rights cover the MCP surface only. The HTTP surface, the web app, the chat and the command
line keep acting on the account key without these rights, until rights per role are built for
them (UC-7.3). The agent key is a bearer key: whoever holds it acts as the person within the
rights of their roles. Taktus cannot tell the person's agent from another holder of the key.
It does not expire; replacing it is how it is withdrawn. The key is not bound to a client, a
host or an address. The surface records every call, and limits none: an agent that calls in a
loop fills the ledger with these entries until the person replaces the key. The tools
are the eleven of §5. Changing a process, steering a run and the emergency stop are not offered
(UC-1.11 §3). A call's act and its `agent.<tool>` entry are written in two transactions: a
failure between them leaves the act without its entry, and the act's own entry then remains
the record. The tools' descriptions and their schemas are part of this surface's interface,
and an agent may still misuse a tool it holds the right to: the right bounds what it can do,
not whether it does it well.
