---
id: UC-1.8
title: A session with project knowledge
component: command
epic: E1
serves: [P2, P6]
state: built
version: 0.5.0
tests: [tests/components/command/test_sessions.py::test_closing_reopening_and_changing_channel_continue_the_same_session, tests/components/command/test_sessions.py::test_every_statement_names_its_source_or_says_it_has_none, tests/components/command/test_sessions.py::test_a_session_reads_only_what_its_participant_may_see, tests/components/command/test_sessions.py::test_a_session_acts_on_nothing_and_settles_in_a_plan_draft_or_a_record, tests/composition/test_session_sources.py::test_each_participant_reads_the_source_as_the_source_shows_them, tests/composition/test_session_sources.py::test_a_participant_without_an_own_credential_gets_nothing_from_the_source, tests/composition/test_session_sources.py::test_a_source_that_refuses_the_credential_gives_nothing, tests/composition/test_session_sources.py::test_the_chat_continues_the_participants_one_session, tests/composition/test_session_sources.py::test_the_chat_answers_nobody_unplaced_and_no_one_outside_the_project, tests/adapters/rest/test_structure_and_administration.py::test_a_project_is_created_referred_to_and_holds_one_session]
adrs: {ADR-0277: b52a68602dad, ADR-0304: e3ea8eccf25f}
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

## 5. What is proven so far

Built by ADR-0277: a session is one participant's in one project, the same one after closing and
on every channel; every statement names its source or says it has none; it reads through the
participant's own sight and acts on nothing, settling in a plan draft or a named record, each
recorded `session.settled`. The web app presents it (`#/structure`, `/sessions`).

Built by ADR-0304: a chat reaches the session. A person the identity component placed says
`session <project>`, `session <project>: <text>` or `session <project> close` in any chat
Taktus reads, and is answered there; the session is the one the web app shows, and its history
holds the turns of both channels. A participant outside the project, or an answer that would
carry a secret value, is told the one sentence instead; a sender nobody placed is not answered.

The project's source systems are read with the participant's own credential for each
(`TAKTUS_SESSION_SOURCES`, with `TAKTUS_PERSONAL_CREDENTIALS`). Against the wiki connector and
the fake of the wiki, two participants whose tokens the wiki shows different books each read
what it shows them; one without a credential of their own gets nothing, and the source is not
called; a source that refuses the credential gives nothing.

Not yet: a repository is read only through a search in the shape of
`knowledge.documents.search`, and the shipped repository connector offers none, so a
repository reference is read as a reference. The chat is proven at the channel's reader, with a
recording of its deliveries; on an instance, with the chat connector and its service, it waits
for a person. The state is `built`.
