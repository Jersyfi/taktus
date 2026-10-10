# ADR-0064 — A process version is drawn as its graph, with its autonomy statement and its runs

**Status:** accepted · builds the process level of UC-6.10 (issue #190, DEC-0055) on the shape
ADR-0063 set for every level

## Context
UC-6.10's second level is *the process*: the steps of a process version as a graph, each step
showing how it works. Two of its conditions bear on it directly. A new process version changes
the graph with nothing else edited. The autonomy statement is shown with the process, as
ADR-0026 requires wherever a process is shown.

ADR-0063 set the shape of a level: one request on the surface, composed by `reporting` from the
records of the component that owns them, every element with its glyph with motion and without,
followed live from the stream. Three questions remain for this level.

1. **Which version** a reader sees when they name only the process.
2. **What state a step of a version is in.** The vocabulary gives a step a form by its state.
   A step of a version is not a step run; it has no state of its own.
3. **Who may see a process.** The predicate of `reporting` answers for a run (ADR-0055 §5); a
   process with no run must be answerable too.

## Decision

### 1. The active version by default, any registered version by name
`GET /levels/processes/{process_id}` draws the process's active version: the one registered last,
whose triggers fire (ADR-0035). `?version=` names any other registered version. The level lists
every registered version and says which is active, so that a reader moves between them. The graph
is read from the version's record each time and never stored: a newly registered version is the
active one at the next read, with nothing else edited.

### 2. A step is at rest, or running in the runs that run it
A step of the version is drawn in the state `running` while at least one run of that version that
the reader may see has its step run in that state, and in the state `planned` otherwise. The
graph is the version's plan, and `planned` is the vocabulary's still form of a step that belongs
to a plan and does no work. The level names the runs each step is running in. So only recorded
work moves, as UC-6.10 *motion means something* requires; a version no run is running draws no
motion. No new token enters the vocabulary.

Each step's text says how it works: the method kind, its family and exactness class, why that
method was chosen, the method kinds considered and not chosen, where it falls back, which steps
it follows (CLAUDE.md §3).

### 3. The process, with the runs of the version the reader may see
The level carries the autonomy statement as the version states it, and in words: the level, its
reason, what is missing to go higher, and each tool action's own level and reason. It carries the
runs of the version, newest first, each with its glyph, leading down to its run level. The run
level leads back up by its process version.

### 4. The predicate answers for a process too
`reporting`'s visibility module gains `may_see_process`. Until UC-6.4 it is the tenant boundary,
like `may_see`. A process the reader may not see is answered `404`, exactly as one that does not
exist. Every run of the version is asked of `may_see` one by one; a run withheld is neither drawn
nor counted, and no step is drawn running for it.

### 5. Live through the process scope
The web app follows `GET /changes?process=…` and reads the level again on the snapshot and on
every change, as ADR-0063 §3 says for every level.

## Alternatives
- **The newest version by name, not the active one.** Versions are named by their authors and
  carry no order the record states; the active one is the one that runs.
- **A state of its own for a step of a version — *at rest* — in the vocabulary.** It would draw
  the same as `planned` and need a state the run component does not have; the vocabulary's test
  holds the two lists of states equal.
- **Count the runs per state on every step.** A figure on every node — how many runs failed at a
  step — is the bottleneck analysis of UC-9.5, a figure of its own with one definition, and is not
  invented here.
- **Draw the runs of every version on the graph.** A run of version 1 says nothing about the steps
  of version 2.

## Consequences
- The surface gains `GET /levels/processes/{process_id}`.
- `reporting` gains the process level beside the run level, and `may_see_process`; the
  composition root's level records read the process's repositories as well as the run's.
- The web app gains `#/processes/<id>` and `#/processes/<id>/<version>`; a run's level and the
  list of runs link to their process.
- The web app's fixtures gain a process level, drawn by `reporting`.

## Where this promise ends
A step is drawn running only for runs whose step run is recorded `running`; a step that waits, is
admitted, or failed draws at rest, and the run level says why. The runs listed are those of the
drawn version; a run of another version appears on that version's graph. The active version is
the one registered last; a version registered and refused (ADR-0039) is never drawn because it
was never stored. Until UC-6.4 the predicate is the tenant boundary, so any identity of a tenant
sees every process and run of it. The level reads every run of the tenant to find those of the
version; a tenant with very many runs makes the read slower, and an index for it is left until a
measurement asks for one. What a process does once it is changed is pair editing's, not this
level's: the level shows, it changes nothing.
