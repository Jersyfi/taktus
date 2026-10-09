---
id: UC-1.8
title: A session with project knowledge
component: command
epic: E1
serves: [P2, P6]
state: specified
version: 0.3.0
tests: []
adrs: {}
supersedes: null
---

# UC-1.8 — A session with project knowledge

## 1. What must be achieved

Besides running processes, a person works out ideas with Taktus: thinking through alternatives,
shaping a process change together. A session for that is persistent and bound to a project. It
reads what the project knows — its repository, its documents, its decisions, its run history — and
it ends, when it ends in something, in a command or a new process version. The same session is
reached from the web app and from chat.

## 2. How it is verified

- A session belongs to one project. Closing it and opening it again, or moving from the web app to
  a chat channel, continues the same session with its history.
- Every statement in a session drawn from the project's knowledge names its source.
- A session reads only what its participant may see. The permissions of the source system apply
  as they apply to the participant.
- A session acts on nothing directly. What it produces is a plan commissioned under UC-1.2, or a
  process version registered like any other.
- What a session settles that later work needs is recorded where that work will find it — a plan,
  a process version, a decision record — and not only in the session.

## 3. Where the boundary lies

**Not the knowledge layer.** How sources are connected and read is the `knowledge` component's
(UC-5.5). **Not a chat tool of its own**: the session is presented in the
web app and in the organisation's own chat channel. **Not a person's assessment**: nothing in a
session is used to judge its participant (principle 14).

## 4. What it rests on

Blueprint UC-01, `AF-01-dev-orchestration.md` §6, which first described it; the roadmap's `0.3.0`,
"sessions with project knowledge", hence the version; the plan (UC-1.2); the process version
(UC-4.1); the command and its reply channel (UC-1.1). UC-1.8 is in no version of the definition; it
was numbered in conversation (`NUMBERING.md`).
