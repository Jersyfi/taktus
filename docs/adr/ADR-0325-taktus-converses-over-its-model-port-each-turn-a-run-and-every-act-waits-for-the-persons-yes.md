# ADR-0325 — Taktus converses over its model port: each turn a run, and every act waits for the person's yes

**Status:** accepted · extends ADR-0277, ADR-0304, ADR-0261, ADR-0008, ADR-0324 · UC-1.14, DEC-0239

## Context

The owner could not find how to talk to Taktus. Five surfaces each read a little: the plan
dialogue's guided questions, the chat's phrasebook, a session in a project, the tools of a
person's own agent, and the command line. Only two processes read free language with a model:
a change in dialogue (S-07) and a process from a description (S-08). The session of ADR-0277
has a port for a counsel that thinks a question through, and nothing behind it.

DEC-0239 decided "both, Taktus leads". A person's own agent may build (ADR-0324), and Taktus gets
a conversation of its own, over its own model port, in the web app and the chat, as easy to
use as a chat assistant. A vendor's agent program never leads that conversation
(`docs/vision/non-goals.md`; UC-1.1); it may only serve as a worker inside a step.

Four things already hold and must keep holding. Every act on the control plane acts as one
identity. A language model never produces an `exact` value. A free-text answer is read back and
confirmed before it counts (ADR-0008). Every call of a model is budgeted and in the ledger,
because it is a step of a run (control-plane.md §1).

## Decision

### 1. A conversation is one person's, in a tenant, tied to no project

A **conversation** (`Conversation`, command component) is one person's running exchange with
Taktus in one tenant: their turns, Taktus's answers, and the acts Taktus proposed with their
state. It is one record whatever channel a turn came through, found by an identifier derived
from the tenant and the person. It keeps the last 200 turns. It is stored in the table
`conversation` (migration `0113`), under row-level security like every table.

It is not the session of ADR-0277. A session belongs to one project and names a source for every
statement. A conversation belongs to no project, and its answers are Taktus's own. The session
stays as it is; its counsel port stays unanswered (§6).

### 2. Taktus proposes acts only from the closed list

The acts Taktus may propose are the closed list of ADR-0324 §1, and only they. Reads are not
acts: what the person may see is given to the model with the turn (§3). An act proposed is
checked by rule — on the list, its arguments declared and of their kind, on a process the
person may see — and read back by rule (`composition/building.py`). An act that fails the check
is not kept, and the answer says so.

### 3. Every turn is a run of a process the operator names

A turn is kept, and a run of the conversation process starts as the person. The operator names
that process (`TAKTUS_CONVERSATION_PROCESS`); it is a tenant's bundle, never a default of the
product (ADR-0092). The repository ships S-09 (`blueprints/self-operation/`):

| Step | Method | Exactness | What it does |
|---|---|---|---|
| `context` | rule | sourced | reads the message, up to twelve turns before it, the closed list of acts, and the processes and open plan drafts the person may see, through the loopback connector |
| `think` | llm | free | answers in words, and names at most one act with its arguments, as one JSON object |
| `answer` | rule | exact | keeps the answer as Taktus's turn; checks the act and reads it back by rule; keeps it waiting |

Because the turn is a run, its model call is budgeted, its steps are in the ledger, and its
provenance is written, as for any run. This is the pattern of the rollout channel's assistant
(ADR-0261): a person's message is an input of a process, never a command.

The only value a model produces is `free`: an answer in words and a proposal. The `exact` value
of the run — whether the act is on the list and fits — is produced by a rule. An answer the rule
cannot read as the agreed form is kept as "no answer could be formed", and no act is kept.

### 4. Only the person's yes acts

An act waits in the conversation, `waiting`, until its person says yes or no. A yes does the
act through the services every surface uses, as the person; a no records that nothing was done.
What came of it — the draft opened, the run started, the refusal — is Taktus's next turn, with
links to what was created. Either is a ledger entry with the person as actor. Nobody else
settles a person's act.

### 5. The surfaces

- **The web app.** `GET /conversation`, `POST /conversation` (`202` with the run) and
  `POST /conversation/acts/{act}` with `yes`. The page "Ask Taktus" (`#/ask`) shows the turns,
  a card for each act with "Yes, do it" and "No", and the links of what was done. It asks for
  the conversation again while a run is forming the answer.
- **The chat.** ADR-0326.
- **A person's own agent** confirms acts with `confirm_act` (ADR-0324 §3); it has no turns.

### 6. The project session's counsel stays unanswered

ADR-0277's `Counsel` port is a synchronous call inside a request. A call of a model there would
be no run: no budget, no step in the ledger. It is therefore not answered by the model port.
A session in a project keeps answering with the passages of the project's knowledge, each naming
its source. A person who wants Taktus's own reasoning asks in the conversation.

## Alternatives

- **A vendor's agent program as the engine.** Rejected: `docs/vision/non-goals.md` keeps an
  agent runtime out of the core, and UC-1.1 keeps the conversation Taktus's. Such a program may
  serve as a worker inside a step.
- **The model port called inside the request.** Rejected: the call would be outside any run,
  so outside the budget and the ledger. A turn would also hold a request open for as long as
  the model takes.
- **The model calls tools in a loop.** Rejected: the model port is single-turn and offers no
  tools (`ports/model.py`). One proposal per turn, read back, keeps every act with the person.
- **The session of ADR-0277 without a project.** Rejected: a session's every statement names its
  source in the project's knowledge; a conversation without a project has none to name.

## Consequences

- New: the record `Conversation` and its table (migration `0113`), the setting
  `TAKTUS_CONVERSATION_PROCESS`, the capability `orchestrator.conversation` of the loopback
  connector with `context` and `answer`, and S-09.
- The ledger gains `conversation.said`, `conversation.answered`, `conversation.act_confirmed`
  and `conversation.act_declined`, each with the person as actor. No measure is computed from
  them per person (principle 14).
- An instance without the setting has no conversation; the page says so, and names the setting.

## Where this promise ends

The conversation answers from what it is told: the message, twelve turns before it, the list of
acts and the names of what the person may see. It does not read a process's steps, a run's
results or the knowledge system; an answer about them is the model's, and may be wrong. The rule
checks that an act is on the list and fits; it does not check that the act is what the person
meant — the read-back and the person's yes do. One turn is answered at a time: a turn while a
run is still forming the last answer is refused, until that run ends. A run that waits on a
person — the model unreachable, its fallback the owner — ends the wait for the conversation only
in that it is said as "no answer was formed". The answer arrives when the run reaches its last
step; the web page asks for it again every few seconds and does not stream it. How short and how
good an answer is depends on the model the purpose `reasoning` resolves to.
