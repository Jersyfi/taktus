# ADR-0304 — A session is reached from the chat, and reads the project's sources with the participant's own credential

**Status:** accepted · extends ADR-0277, ADR-0264 · UC-1.8, DEC-0236

## Context

ADR-0277 built the session of UC-1.8: one participant's in one project, the same one after
closing and on every channel, every statement naming its source. Two parts of UC-1.8 §2 were
left open. A chat channel did not reach the session; only the web app did. And the session read
only what Taktus keeps of a project — its references, its processes. What the project's source
systems hold — its repository, its documents — was not read, because UC-1.8 §2 says that the
permissions of the source system apply as they apply to the participant. That needs the
participant's own credential for each source system.

ADR-0264 already decided where a person's own credential comes from: the instance's
configuration `TAKTUS_PERSONAL_CREDENTIALS` maps, per identity, a parameter a call names to the
parameter of that identity's own credential. Without an entry, nothing is read.

## Decision

### 1. A message in a chat reaches the participant's session

A person the identity component placed says, in any chat Taktus reads, one of three things:

- `session <project>` — the session is opened, or continued, and Taktus answers how many turns
  it holds and what it last settled;
- `session <project>: <text>` — the text is said in the session, through that chat's
  capability, and Taktus's answer is said back, each statement with its source or the words
  that it has none;
- `session <project> close` — the session is closed; opening it again continues it.

The word `session` is fixed. It is read in every conversation, not only the owner's, because a
session is every participant's. The session is the one `Sessions.open` returns for the
participant and the project, whatever channel the message came from. So the web app and the
chat continue one history. A sender nobody could place is not answered here; the identity
component offers them a link, as for every other message. A participant who does not belong to
the project is told that there is no such project of theirs. An answer that would carry a secret
value the instance holds is not sent, and that same sentence is said instead.

The chat is read in `composition/sessions.py` (`SessionsInChat`), handed to the owner channel's
chain of readers (`OwnerAnswers.sessions_with`). It is wiring, because it crosses the command
component's sessions and the reporting component's deliveries.

### 2. A source system is read with the participant's own credential, or not at all

A project refers to its source systems by its references (ADR-0276): a reference has a kind —
`document`, `repository` — and a link. The composition configures, per reference kind, a
**source system**: the connector operation that searches it, and the credential parameter that
operation names. A source system is reached by capability through the connector port, never by
a product's name.

For each reference of a configured kind, `SourceKnowledge` asks `PersonalCredentials` for the
participant's own parameter. Where there is one, the operation is called with that parameter
alone, as the participant (`CallContext.identity`). Where there is none, the source is not
called, and nothing of it reaches the session. A source that refuses the credential
(`unauthenticated`, `forbidden`) or is not reachable gives nothing either. It is never read with
a credential of Taktus's own instead.

The operation is a search: its input is the participant's words (`query`) and how many documents
to return (`count`); its output names `documents`, each with a `title`, a `url` and a `body`.
This is the shape of `knowledge.documents.search` (ADR-0265). Every document read becomes one
passage, whose source is the document's title and its link. A passage from a source system
stands beside what Taktus keeps of the project, and both carry their source to every statement
drawn from them (ADR-0277 §3).

### 3. Nothing a session reads in a source is stored outside the session

A passage is not recorded in the ledger and not kept as a copy of the source. What the session
said from it is the session's turn, with the link to the source, as before.

## Alternatives

- **Read a source with the process's credential, and filter by the participant's rights in
  Taktus.** Taktus does not know a source system's own permissions; filtering them again would
  read wider than the participant and decide by a copy of rules it does not hold. Rejected by
  UC-1.8 §2 and ADR-0264 §3.
- **A chat of its own for sessions.** UC-1.8 §3: not a chat tool of its own.
- **Bind a chat thread to a session.** It would need a binding to be stored and found again,
  and a thread differs per chat product. Naming the project in each message needs nothing
  stored, and the participant and the project already name exactly one session.

## Consequences

- `composition/sessions.py`: `SourceSystem`, `SourceKnowledge`, `SessionsInChat`.
- `composition/owner_channel.py`: `OwnerAnswers.sessions_with`, read right after an answer to
  a report and before every other reader of the chain.
- `composition/workspace.py`: `workspace_of` takes what reads a project's knowledge beside
  what Taktus holds; `StructureKnowledge.references` gives a project's references where the
  participant may read in it.
- `composition/settings.py`: `TAKTUS_SESSION_SOURCES`, `document=knowledge.documents.search/
  KNOWLEDGE_TOKEN`, parameters only. The daemon resolves each source's connector by the
  operation's capability through its connector pool, and reads the participant's own
  parameter from `TAKTUS_PERSONAL_CREDENTIALS`.
- Tests: `tests/composition/test_session_sources.py`, against the wiki connector served over
  MCP and the fake of the wiki, with one token per participant, and the chat's reader through
  a recording of the channel's deliveries.

## Where this promise ends

- What a source system shows the participant is that system's answer to the participant's own
  credential. A credential that permits more than the participant should see is the source's or
  the operator's error, as ADR-0264 states.
- Only a source system that offers a search in the shape of §2 is read. A repository is read
  through such a search where its connector offers one; a connector that offers only reading
  files by path is not a source system of a session.
- The word `session` is English. The phrasebook of the owner's conversation does not translate
  it.
- A passage read from a source is not checked against the source again before the session
  quotes it. A source that changed since the turn shows its new text at the link.
