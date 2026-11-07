# ADR-0277 — A session belongs to one participant in one project, and names the source of every statement

**Status:** accepted · extends ADR-0237, ADR-0276 · UC-1.8, DEC-0228

## Context

UC-1.8 asks for a persistent session in which a person works out ideas with Taktus, bound to a
project and reading what the project knows. Closing it and opening it again, or moving from the
web app to a chat channel, continues the same session. Every statement drawn from the project's
knowledge names its source. A session reads only what its participant may see, and acts on
nothing: it ends in a plan commissioned under UC-1.2, or a process version registered like any
other, and what it settles is recorded where later work finds it.

## Decision

### 1. One record per participant and project

A `ProjectSession` is the command component's record of one participant's conversation in one
project. `open` returns the one the participant had in that project, reopened if it was closed;
a new one only the first time. Every turn carries the channel it was said through, so the web
app and a chat continue one history. A session is never another participant's: every call names
the participant, and a session of someone else is unknown to them.

### 2. Entering a project is the structure's answer

Whether a participant may open or continue a session in a project is asked of `ProjectAccess`,
which the composition answers from the organisation's structure (ADR-0276): the participant
belongs to the project, or the project is a shared one their context sees. It is asked again at
every turn, so a participant who left a project reads nothing more of it.

### 3. Every statement names its source, or says it has none

What the project knows is read through `ProjectKnowledge`, as the participant: the composition
answers it with what that participant may see. A statement is either drawn from one of the
passages read for the turn, and carries that passage's source — a title and a link — or it is
said as not drawn from the project's knowledge. Where a counsel (a model, behind the model port)
thinks a question through, it names the passage of each statement by its index; a source it was
not given is no source. Without a counsel, Taktus's answer is the passages themselves, each with
its source.

### 4. A session acts on nothing, and records what it settles

A session settles in a plan draft of the plan dialogue (`to_plan`, ADR-0237) — commissioned
there, or not at all — or names a proposed process version or a decision record it settled
(`settle`). Each outcome is kept in the session and recorded `session.settled` in the ledger,
naming the command the plan draft answers where there is one. A turn is no ledger entry: what a
person says in a session is no measure of them (principle 14).

## Alternatives

- **A chat history per channel.** Two histories of one conversation drift apart, and moving
  from the web app to the chat would start again.
- **A session that may act.** UC-1.8 forbids it: the plan dialogue and the process registration
  are where acts are commissioned.
- **Statements without sources unless asked.** A reader cannot tell a fact of the project from a
  guess; UC-1.8 asks that every drawn statement names its source.

## Consequences

- `components/command/domain/model/session.py`, `application/service/sessions.py`
  (`Sessions`, `ProjectKnowledge`, `ProjectAccess`, `Counsel`).
- Migration 0107: `project_session`.
- `tests/components/command/test_sessions.py`.

## Where this promise ends

- What a source system lets the participant read is that system's answer to the participant's
  own credential. Reading a source system's content as the participant needs a credential of the
  participant for it; until one is configured, `ProjectKnowledge` reads only what Taktus holds
  that the participant may see — the project's references, its processes and their runs.
- The counsel's reasoning is not checked against its sources beyond the index it names.
- A session is not shared between participants; a project team works in one project, each in
  their own session.
