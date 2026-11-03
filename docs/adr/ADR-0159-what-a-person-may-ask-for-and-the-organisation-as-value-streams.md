# ADR-0159 — What a person may ask for, and the organisation as value streams

**Status:** accepted · extends ADR-0029 (reporting reads, owns no figure), ADR-0131 (a person's
own agent) and ADR-0146 (a person's step names a role) · issues #340 and #338, UC-1.13 and UC-15.6

## Context

Two views were missing, and both were accepted with the product outlook of 2026-10-12
(DEC-0190).

- **What a person may ask Taktus for.** A person can start a process from the command line, from
  their own agent and, for an intervention, from a reply in the chat. Nobody can see which
  processes they may start. The outlook warns that the step from such a list to a ticket portal
  is small (principle 1).
- **The organisation as value streams.** UC-15.4 declares a chain of processes but builds none
  before `0.7.0`. A person cannot see which processes carry a customer's need to its outcome,
  where people act along it, or where it crosses from one department to another. Package A gave
  every person's step a role (ADR-0146), so the lanes can now be drawn honestly.

Four facts shape the decision.

- Every channel's start already took the same path: a command, a commissioned plan, a run
  (control-plane.md §1). Only the command itself was built three times, and the agent's said
  `start` where the command line's said `run`.
- Reporting reads what other components own and stores no figure (ADR-0029).
- A figure for a role held by one person is that person's figure (ADR-0015).
- The structure of an organisation is each identity's `org_path` (ADR-0040). It stays.

## Decision

### 1. The catalogue is a projection of the active versions

`GET /catalogue` lists every process with an active version that the reader may see, by the
predicate every level is read through. Each entry says what the process is for, the inputs it
needs, the level it runs at and the roles a person acts in along it. It names the one start
command (§2) and how to start the entry on each channel: the web app's route, the chat's words
and the tool of the person's own agent, with whether a role of theirs grants the right it needs.

The catalogue keeps nothing. There is no request object, no queue and no promised time. A start
is a run, and the run's view tracks it. The pure view is `reporting/domain/service/catalogue.py`;
the composition root's `AgentSurface` gathers its facts.

### 2. One start command for every channel

`command/domain/service/start.py` builds the command that starts a process. Its intent is
`run <process>@<version>`, recognised as `process.run`; the inputs are its context. The command
line, the person's own agent, the web app's list and the chat all build it there. Only the
channel, the reply address and who asked differ.

`POST /catalogue/{process}/start` starts the entry from the web app on `channel.web`, acting as
the person. It needs no right beyond seeing the process, as the command line needs none beyond
an identity. The agent's tool keeps needing `agent.start` (ADR-0131 §3), because an agent acts
without the person watching each call.

### 3. The chat reads the catalogue and a start

The owner-facing channel reads two more requests by its phrasebook's words. `what can I ask for`,
standing alone, lists the entries with what to write to start each. `start <process>` is read
back, and the process starts only on the same person's `yes` in the same thread (ADR-0008). A
process that needs an input a reply cannot give is listed with its inputs and started from the
web app. Only the owner and the people the owner named are answered, as for every other act in
that conversation (UC-1.7). The start runs on the conversation's channel, as the person who
confirmed it.

### 4. A value stream is a definition of the process component

A value stream has a kind — `core` from the customer's need to the customer's outcome, or
`management` or `support` beside the core streams — a trigger, an outcome, one responsible role
and its processes in the order they hand over to each other. That ordered list is UC-15.4's
chain. When the chain's handover clauses are built, they extend this object. No second object is
made.

It lives with the processes: `process/domain/model/stream.py`, declared through
`ValueStreams.declare`. Each declaration is a revision of its own, `<stream>@<revision>`, stored
in `value_stream` (migration `0088`). A revision is never overwritten. A declaration that says
what the current revision says keeps nothing. Each kept revision is the ledger entry
`value_stream.declared` with the declarer and a digest. Only a person who holds the role `owner`
declares one, at `PUT /streams/{stream}`, because a stream says where responsibility lies.

### 5. The map is read from the records, and stores nothing

`GET /streams` draws three tiers: management, core and support. For each stream it reads its
processes' active versions, the runs of them that finished in the window and the blocks of those
runs. It shows:

- the **autonomy mix**: the share of its steps at each level;
- the **method mix**: the share of its steps by method kind, reproducible kinds first;
- the **flow efficiency**: of the lead time of those runs, the share in which nothing was
  blocked;
- the **blocked share**, the rest, and the account that held up most;
- the **department boundaries it crosses** (§6).

The processes no stream names are listed too. A process the reader may not see is left out of
every figure. The pure view is `reporting/domain/service/streams.py`; `composition/streams.py`
gathers the facts. The runs are read newest first and the reading stops at the first one older
than the window (ADR-0094).

### 6. A stream opens as role swimlanes, with the structure overlaid

`GET /streams/{stream}` draws one stream. Each process is a column, in the order of the stream.
The lanes are Taktus's reproducible methods, its variable methods, and one lane for each role a
person acts in, in the order the stream first needs it. A `human` step sits in its role's lane;
one that names no role sits in the owner's, as the stage view shows a wait that names none.
A step that falls back to a person also marks that role's lane.

A **unit** is one identity's `org_path`, joined by `/`. A role sits in the units its holders sit
in. A **department boundary is crossed** where a person's step hands over to the next person's
step and their two roles share no unit. A role nobody holds sits in no unit and crosses nothing.
`org_path` stays as it is: the lanes carry the units, and the web app's toggle overlays them.

A role's waiting is shown only where at least two identities hold the role (ADR-0015). A unit
is shown, never a count of who sits in it. No field of either view can hold a person.

## Alternatives

- **A request object for what a person asked for.** Rejected: it is the ticket the outlook
  warns of, and the run already records the request.
- **A right of its own for a start from the web app.** Rejected for now: the web app acts with
  the person present, as the command line does. A tenant that needs one asks for UC-7.3's
  rights per role, which can narrow the predicate without a second path.
- **The value stream as a file of the bundle.** Rejected: a bundle is one process, and a stream
  spans several. A stream changes when processes are added, not when one is versioned.
- **The department as a field of the process.** Rejected: it would be a second structure beside
  `org_path`, and two answers to the same question drift apart (principle 7).
- **The flow efficiency per stream run.** Not possible yet: a run across a whole stream exists
  only once UC-15.4's chain runs. Until then a stream's runs are its processes' runs.

## Consequences

- `command/domain/service/start.py`; the command line's `_command` and `AgentSurface.start`
  build their command there. The agent's command reads `run <ref>` where it read `start <ref>`,
  and carries no empty context.
- `AgentSurface.catalogue`; `rest/catalogue.py` with `GET /catalogue` and
  `POST /catalogue/{process}/start`.
- `composition/catalogue_in_channel.py`; the phrasebook's eight entries from `catalogue_words`
  to `start_not_done`; `PendingAct` of kind `start`.
- `process/domain/model/stream.py`, `process/application/service/streams.py`, the table
  `value_stream` and migration `0088`; the ledger kind `value_stream.declared`.
- `IdentityDirectory.role_units`; `composition/streams.py`; `rest/streams.py` with
  `GET /streams`, `GET /streams/{stream}` and `PUT /streams/{stream}`.
- The web app's pages `#/catalogue`, `#/streams` and `#/streams/{stream}`.

## Where this promise ends

- **The catalogue lists what a person may see, not what they may do everywhere.** Until UC-6.4
  narrows the predicate, a reader sees every process of their tenant. A start the run refuses —
  a missing input, a budget — is refused after the entry was listed.
- **The chat starts only what needs no input.** An entry that needs one is started from the web
  app or by the person's own agent.
- **The chat answers only in the owner's conversation**, and only the owner and the people the
  owner named.
- **A stream's figures are its processes' figures.** No run spans a stream before UC-15.4's
  chain is built (`0.7.0`), so the flow efficiency and the blocked share are those of the
  processes' own runs, summed. The waiting at a handover between two processes is not measured.
- **A department is a unit of `org_path`, read as written.** A role whose holders sit in several
  units crosses no boundary into any of them. A structure written coarsely shows few crossings.
- **Nothing is simulated.** The level a stream would reach, and the hours a change would move,
  are not shown; UC-9.1's simulation is its own.
- **The responsible role is a name, not an anchor.** A raise inside a stream goes where it went
  before. Whether the stream's role or the domain's owner decides when the two disagree is
  UC-15.5's, and open.
