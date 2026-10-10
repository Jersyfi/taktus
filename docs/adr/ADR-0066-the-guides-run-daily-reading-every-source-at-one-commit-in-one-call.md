# ADR-0066 — The guides run daily, reading every source at one commit in one call

**Status:** accepted · makes the daily process of UC-13.6 buildable (issue #198) on ADR-0065,
ADR-0035 and ADR-0045

## Context

ADR-0065 renders the guides from the repository and puts them into a knowledge system without
overwriting a hand edit. A person runs it: `taktusctl guides publish` reads a checkout through
`git`. UC-13.6 §2 asks for more. Generating the guides is a process of Taktus, with its steps,
methods and ledger entries. It runs at least once a day. A hand edit is reported to the person
responsible for the documentation. Switching the process off leaves the repository's
documentation complete.

ADR-0065, *Where this promise ends*, left one question to this decision: how a run reads every
source file at one commit through the repository capability. A process reaches the repository
only through `repository.files` (CLAUDE.md §6). It has no checkout and no `git`.

Three facts shape the answer. A page names the commit it was rendered at, so every part of every
page must come from that commit. A branch can move while a run reads. And a bundle's steps are
fixed when it is written: a step cannot repeat itself once per file the manifest happens to name.

## Decision

### 1. One call reads every source at one commit

The repository capability gains a read, **`repository.files.read_many`**. It takes up to 100
paths and a ref. It resolves the ref to a commit once, reads every path at that commit, and
answers the commit with every file in the order asked. A path that names no file at the commit
is answered with content `null`, in its place. The reference connector implements it with one
request for the ref and one per path.

The run reads in two steps. `read-manifest` reads the manifest at the configured ref, and the
answer names the commit the ref resolved to. `read-sources` reads every file the manifest names
at that commit. A 40-character commit is never resolved again, so the manifest and every source
come from the same commit even when the branch moves between the two steps.

### 2. What only the instance can do, it does through the loopback

Rendering, measuring and publishing are the knowledge component's. Raising a report is the
reporting component's. The run component may not import either (CLAUDE.md §6). The process reaches
them the way S-01 reaches the catalog: as the capability **`orchestrator.guides`**, served by the
loopback connector (`docs/architecture/contracts.md` §4). The composition root answers it
(`composition/guides.py`). It has five operations:

| Operation | Effect | What it answers |
|---|---|---|
| `orchestrator.guides.sources` | read | the files the manifest names |
| `orchestrator.guides.render` | read | every page, rendered from the files at the commit; the place below which every guide lies |
| `orchestrator.guides.measure` | read | every page's state against one reading of the knowledge system, and what is done with it |
| `orchestrator.guides.publish` | write, `marked` | every page's action against that reading; a page written is an egress record |
| `orchestrator.guides.report` | read | the reports raised for the pages a person's text stands in |

### 3. The process: S-05 Guides

`blueprints/self-operation/processes/S-05-guides.yaml`. Nine steps, all of method `rule`:

1. `read-manifest`, `sourced` — the manifest and the commit, through `repository.files.read`.
2. `sources`, `exact` — the files the manifest names.
3. `read-sources`, `sourced` — every source at that commit, through `repository.files.read_many`.
4. `render`, `exact` — the pages (ADR-0065 §2).
5. `read-held`, `sourced` — one reading of the knowledge system, through `knowledge.pages.list`.
6. `measure`, `exact` — every page against that reading (ADR-0065 §5).
7. `publish`, `sourced` — the pages written against that reading.
8. `report-edits`, `sourced` — a report of every hand edit.
9. `report`, `sourced` — how many pages were created, updated, kept and withheld.

**Measured once, acted on once.** `measure` and `publish` take the same rendering and the same
reading. The knowledge component's use case accepts the reading instead of taking its own, so
what the run measured is what it acts on. A write still names the text it expects to replace: a
page a person edits between the reading and the write is kept.

**A publication that writes nothing acted on nothing.** The operation is declared `write`, and
every result of an outward operation names its records. When no page is written, it answers
`replayed`, as a repeat does, naming the pages it found as they should be. The ledger then says
that nothing went out.

Its trigger is `daily`: the elected scheduler starts one run every day at 00:00 UTC
(ADR-0035). The trigger gives every input, because a scheduled run has nobody to ask.

### 4. A hand edit reaches the person responsible, once

The person responsible for the documentation is a **role** the bundle names, `documentation`. A
report of a hand edit goes through the tenant's owner-facing channel when the channel carries
that role (ADR-0045 §3). For this tenant the channel reaches the owner.

The report is of kind `need`: something only that person can provide, the decision whether the
edit becomes a change to the repository. It holds the difference, the steps to keep or drop the
edit, the page that stands still, and a date the configured number of days after the run. Its
identifier is derived from the guide, the page and the digest of the text that stands. Raising a
report is idempotent by its identifier, so a daily run that finds the same edit again tells
nobody twice. An edit made on top of it is another text and another report.

A tenant whose channel carries no such role cannot be told. The step `report-edits` then fails
and names the role. The edit is not dropped silently, and the page stays as the person left it.

### 5. A process can be switched off

`taktusctl deactivate --process <id>` takes the process's active version away. Its schedule and
event triggers start nothing, because both read the active version. Its versions stay, and
registering one again switches it back on. The act is the ledger entry `process.deactivated`.
S-05 never writes to the repository, so switching it off leaves the repository's documentation
as it was.

### 6. The instance can serve a directory

Where the organisation keeps no wiki, `TAKTUS_KNOWLEDGE_DIRECTORY` names a directory. The instance
then serves `knowledge.pages` over it with the directory connector of ADR-0065 §6, inside the
instance, as it serves the loopback.

## Alternatives

- **One call of `repository.files.read` per file.** Rejected: a bundle's steps are fixed, and the
  number of files is the manifest's. A step per file would make the bundle restate the manifest,
  a second source of truth for which files the guides take.
- **A loop in the bundle language.** Rejected: it would change what every bundle can say and how
  every run is admitted and estimated, for one process. A read of many files is an ordinary
  operation of the capability.
- **The loopback reads the files itself, through the repository connector.** Rejected: the bundle
  would no longer show that the process uses `repository.files`. The removal test reads the
  bundle's operations to find which processes an integration serves (S-01), and would call the
  repository connector unused by this process.
- **The whole repository as one archive.** Rejected: it transfers every file for the sake of
  about twenty, and the archive is not a shape the capability declares.
- **A worker with a checkout renders the guides.** Rejected: rendering is a rule of the knowledge
  component, `exact`, and needs no sandbox; a worker would add a network path and a clone for it.
- **Each page written by its own step through `knowledge.pages.write`.** Rejected for the first
  alternative's reason: the number of pages is the manifest's.
- **A report kind of its own for a hand edit.** Rejected: a kind adds sentences to every
  phrasebook, and every tenant's own phrasebook would stop validating until its owner wrote them.
  A need already holds what is needed, the steps, what stands still and a date.

## Consequences

- The reference repository connector declares and implements `repository.files.read_many`.
- The loopback connector declares `orchestrator.guides`, and `composition/guides.py` answers it.
  `docs/architecture/contracts.md` §4 lists it.
- The knowledge component's publishing takes an optional reading, `PublishGuides.held`; its
  domain gains `measure` and the text of a hand edit's report (`domain/service/edits.py`).
- The process component gains `DeactivateProcess`, and the ledger the kind `process.deactivated`.
- The setting `TAKTUS_KNOWLEDGE_DIRECTORY`.
- `blueprints/self-operation/` gains S-05. Its README says how a person does the same by hand.

## Where this promise ends

- **One call reads at most 100 files.** The guides name 15 today. A manifest that names more is
  refused by the read, and the run stops there; splitting the read is then the change to make.
- **One commit, not one moment of the knowledge system.** The pages are measured against one
  reading. A page edited after the reading is kept by the write's expected digest, but its
  difference is reported at the next run, not this one.
- **The contents page is written from the states the run measured.** Where a write is refused
  because a page changed after the reading, the contents page may name that page as current
  until the next run.
- **Only the owner, or whom the owner named, can be the person responsible.** The owner-facing
  channel reaches them and nobody else (ADR-0045). A tenant whose documentation is someone
  else's cannot name that person yet.
- **The report carries the whole difference.** A very long edit makes a very long message. The
  chat service may cut it; the report's view and its repository text keep it whole.
- **Switching off takes effect at the next trigger.** A run already started ends as it would
  have.
- **Daily is 00:00 UTC.** The schedule is the bundle's; a tenant that wants another hour registers
  a version with another trigger.
