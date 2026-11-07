# ADR-0294 — A connector call is admitted by one rule, from the catalogue's share and the structure's placement

**Status:** accepted · extends ADR-0246, ADR-0247, ADR-0275 · UC-1.4, UC-1.6, UC-8.8

## Context

Two records say who may use a connector.

- **The catalogue's share** (ADR-0246) names one or more circles. A circle is a path of the
  structure or one identity. The engine already asks it before a connector call, through the
  run's port `Shares`. A run whose identity is inside no circle is refused before the call, with
  `frame.refused`, outcome `outside_circle`.
- **The structure's placement** (ADR-0275 §5) puts a connector in one unit. The processes of
  that unit and of every unit below it use it (`usable_by`). Nothing in the run held this. A
  process of a unit the connector was not placed for called it as before.

UC-1.4 and UC-1.6 require that sharing follows the structure. A process moved to another team
uses what the new team shares, with nothing else configured. Two answers held in two places, one
enforced and one not, would let them disagree.

## Decision

### 1. One predicate, asked once before every connector call

The run's port `Shares.connector_call` takes the run's process beside its identity. The
composition root answers it (`composition/shares.py`, `SharesOfTheRun`). A connector call is
**admitted** when both hold:

- the run's identity is inside the connector's share, where the catalogue holds one;
- the run's process may use the connector by the structure, where the structure places it.

A connector the catalogue does not share is the tenant's. A connector the structure does not
place is in the root, which every process uses. Each source can only narrow. Neither widens what
the other or the operator's configuration allows.

### 2. The process's unit is read when the call is made

The structure is asked where the process is placed now, through `usable_by`. A process moved
between two of its runs uses, from its next call on, what its new unit may use. This is the
answer UC-1.4's test reads.

### 3. A refusal is the same refusal, whichever source gave it

A call the predicate refuses never reaches the connector. The step fails without a retry, and
`frame.refused` is recorded with outcome `outside_circle`, as ADR-0246 §3 records it. The
reason names the source that refused: the share's circles, or the units of the placement and of
the process. The engine does not know there are two sources.

### 4. The components stay apart

The run component sees the port only. The catalogue and the identity component do not import
each other. The composition root joins them, as it does for the run's `OrgUnits`.

## Alternatives

- **Copy the placement into the share, or the share into the placement.** One record would then
  be derived from the other and drift whenever one was changed alone.
- **Ask the structure in the engine through a port of its own.** The engine would hold two rules
  for one question, and a third source later would be a third rule.
- **Use the run's recorded unit (`Run.org_unit`).** Where no process is placed it is the
  command's department name (ADR-0166), not a unit of the structure, and cannot be compared with
  a placement.

## Consequences

- `run/ports/shares.py`: `connector_call(..., process=)`.
- `composition/shares.py`: `SharesOfTheRun` takes the structure; `shares_of` passes it from
  `taktusd` and the local composition.
- A tenant that placed a connector in a unit below the root sees processes outside that unit
  refused that connector from now on.

## Where this promise ends

- **Connectors only.** A model, an agent or a skill placed in a unit is not yet held by the
  structure in the run. The catalogue's share still holds each of them as ADR-0246 §3 says.
- **A run's own process.** The predicate reads the process the run runs. A process that a
  connector call reaches through another system is that system's.
- **The placement at the time of the call.** A call already made is not judged again when its
  process moves.
- **Not rights.** Whether a person may run the process at all is UC-7.3's.
