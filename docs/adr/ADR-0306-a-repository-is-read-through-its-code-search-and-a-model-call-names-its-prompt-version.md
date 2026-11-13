# ADR-0306 — A repository is read through its code search, and a model call names its prompt version

**Status:** accepted · extends ADR-0304, ADR-0305 · UC-1.8, UC-5.8, DEC-0236

## Context

ADR-0304 read a project's source systems through a search of documents, with the participant's
own credential. A repository connector then offered no search, so a repository was read as a
reference only. The repository connector now searches code (`repository.code.search`): it
answers the paths of the files whose text contains a text, without their content. Reading them
is `repository.files.read_many`.

ADR-0305 left two things open in UC-5.8. A model call was not linked to the prompt version that
produced it. And the figures of a cost reconciliation were recorded in the ledger only by
digest, so the platform's cost existed only in the platform.

## Decision

### 1. A search of files, then its files read, both as the participant

A source system may be a search of files. Its configuration names the search, the operation
that reads files by path, and the branch it reads at:
`repository=repository.code.search+repository.files.read_many@main/REPOSITORY_TOKEN`.

For a turn, the search is asked for the two longest words of four characters or more the
participant said. The first five paths found are read at the branch, with the same own
credential of the participant (ADR-0264). Each text file read becomes one passage. Its source is
the reference's title with the path, and the reference's link with the path as its fragment.
Without an own credential nothing is called; a refusal of either call gives nothing.

### 2. A model call names the prompt it was made from

The span of every model call (`model.complete`) carries `prompt.name`,
`<process>.<step>`, and `prompt.source`, `<process>@<version>/<step>`. A prompt mirrored to a
platform (ADR-0305 §3) has the same name, and its configuration names the same source. So an
execution and the prompt version that produced it share the name and the source, in Taktus's
trace and in the platform. No product's own attribute name is in the core.

### 3. A reconciliation keeps the platform's cost, and the export carries it

The ledger entry `platform.cost.reconciled` carries the platform's cost of the run as its
consumption, in US dollars. The export (`GET /figures`, `GET /figures.csv`) carries, for the last
reconciliation of each run in the period, `platform.cost` and `platform.cost.difference` — the
platform's cost less the run's own — of the scope `run`. They are read through the run level,
so a run the read API does not show the reader contributes nothing, and each figure reaches only
the roles entitled to it.

## Alternatives

- **The product's own attribute names on the span.** A connected platform would link the call
  to its prompt version by itself. It puts a product's name into the core; rejected by
  CLAUDE.md §6.
- **Asking the search the whole question.** A code search matches a text as written; a question
  as a whole is rarely in a file.
- **A record of its own for a reconciliation.** It needs a table; the ledger entry already is
  the record, and its consumption is what the platform reported.

## Consequences

- `composition/sessions.py`: `SourceSystem.read` and `ref`; `composition/settings.py`: the form
  of `TAKTUS_SESSION_SOURCES` with `+<read>@<branch>`.
- `components/run/application/service/execute_run.py`: the two attributes of `model.complete`.
- `composition/evaluation_platform.py`: the reconciliation's consumption;
  `composition/figures.py`: `platform.cost`, `platform.cost.difference`.
- Tests: `tests/composition/test_session_repository.py`, `tests/components/run/
  test_llm_steps.py`, `tests/adapters/rest/test_figures.py`.

## Where this promise ends

- A code search finds only what the repository service has indexed on its default branch, and
  a text as written: a passage is missed where neither long word is in a file.
- The link is by name and source. A platform that links calls to prompt versions only by its
  own attribute names shows the link only where someone filters by these.
- A reconciliation's figures are the last one's of each run in the period; earlier ones stay in
  the ledger.
