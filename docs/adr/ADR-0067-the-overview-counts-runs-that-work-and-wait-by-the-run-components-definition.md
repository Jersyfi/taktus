# ADR-0067 — The overview counts the runs that work and wait, by the run component's own definition

**Status:** accepted · builds the overview of UC-6.10 (issue #191, DEC-0055) on the shape ADR-0063
set for every level

## Context
UC-6.10's first level is *the overview*: the areas a reader may look into, the processes in
each, and how busy each one is right now. Three conditions bear on it. Motion means something:
an idle system looks idle. A figure has one definition and one value, read from the component
that owns it (ADR-0029). An element the reader may not see is absent and not counted.

ADR-0063 set the shape of a level, and ADR-0064 drew a process version. Three questions remain.

1. **What an area is.** UC-1.4 puts the organisation's structure in the records. Nothing records
   it yet: an identity carries an organisational path, but a process belongs to no unit.
2. **What "how busy" counts.** No component defines it. The run component owns the states of a
   run; the overview may not invent a figure (ADR-0029).
3. **What moves.** The vocabulary moves only a running step (ADR-0059); a run never moves itself.

## Decision

### 1. Until the organisation's structure is recorded, the tenant is the one area
The overview has a list of areas, and today it holds one: the reader's tenant. When UC-1.4
records units and places processes in them, the areas are those units, and the shape of the
overview does not change. The list exists now so that a reader's view does not change shape then.

### 2. How busy a process is: its runs that work, and its runs that wait
The run component defines two sets of run states, beside its state machine:

- **working** — `planned`, `admitted`, `running`: the run has not ended and does not wait;
- **waiting** — `waiting_human`, `halted`, `escalated`: the run has not ended and waits.

A finished run is in neither. The composition root hands `reporting` each run with whether it
works and whether it waits, by these two sets, and `reporting` counts them over the runs the
reader may see. The same two sets give the same counts over the runs the read API returns; a
test holds the two equal. No other figure appears on the overview.

### 3. Only a step running now moves
Each process lists the steps its runs are running right now, each with its glyph with motion and
without, leading down to its run. Nothing else on the overview has a glyph that moves. A tenant
where no step runs draws no motion.

### 4. Visibility, links, and where the web app starts
A process the reader may not see is absent, and so is every run of it; a run the reader may not
see is neither drawn nor counted, by the same predicate as every other level. The overview is
where the web app starts: `#/` follows the tenant's stream and reads `GET /levels/overview` again
on every change. Each process leads down to its process level, each running step to its run
level, and every level leads back to the overview.

## Alternatives
- **The organisational path of whoever activated a version as its area.** It would place a
  process by a person, which is not where UC-1.4 says the structure lives, and it would change a
  process's area when another person registers its next version.
- **One figure, "open runs".** It hides the difference a reader asks first: whether the work
  moves or waits on someone. Two sets cost one more number and say it.
- **Count running steps as the busy figure.** A run waiting for a person is busy for the
  organisation and runs no step; it would read as idle.
- **Define the sets in `reporting`.** `reporting` owns no figure (ADR-0029); the states are the
  run component's.
- **Keep the list of runs as the start page.** It reads the stream into a second model of the
  runs in the browser; the overview says the same from the records, and the process level lists
  each version's runs.

## Consequences
- The run component gains `WORKING` and `WAITING`.
- The surface gains `GET /levels/overview`; `reporting` gains the overview and its port method;
  the composition root reads every process, every version and every run of the tenant for it.
- The web app's start page is the overview; the list of runs it showed before is gone, and
  with it the browser's own model of the runs from the stream.
- The web app's fixtures gain an overview drawn by `reporting`.

## Where this promise ends
There is one area per tenant until UC-1.4 records the organisation's structure; a reader of a
large tenant sees every process of it in one list. The counts are of the runs the reader may
see, and until UC-6.4 that is every run of the tenant. A run is counted by its state as recorded
when the overview is read; a run that changed state since is counted again on the next change.
The overview reads every process, version and run of the tenant on each read; a tenant with very
many runs makes it slower, and a summary kept by the run component is left until a measurement
asks for one. The export of UC-5.7 does not exist yet; the counts are held equal to the read
API's runs until it does. The overview shows no figure about a person, and has no field that
could hold one.
