# ADR-0168 — A BPMN model is read into a plan draft, and a version is written out as BPMN

**Status:** accepted · extends ADR-0011 (process bundles), ADR-0091 (proposal, rehearsal, commissioning) and ADR-0146 (a role, never a person) · issue #345, UC-4.23

## Context

Issue #345 asks that an organisation's existing BPMN models feed Taktus, and that a process can
leave it as BPMN. BPMN 2.0 is an open standard for process models (ISO/IEC 19510), kept as XML.
A model names tasks, the flows between them, gateways where the path splits or joins, and lanes
that say who performs a task.

Three things make the import delicate.

- **A model is not a process of Taktus.** It names no method, no reason for one, no exactness
  class and no fallback (ADR-0004, ADR-0014). Registering it would mean inventing all four.
- **A model is untrusted input.** XML can declare entities that expand to gigabytes, or refer to
  files and addresses outside the document.
- **A lane can name a person.** Taktus never assigns work to a named person (principle 14,
  ADR-0146).

Two words are used below. A **plan draft** is a record of what a model says, with every question
that must be answered before it can become a process. A **projection** is a document derived
from a process version and stored nowhere, as the process diagram is (UC-4.2).

## Decision

### 1. The format lives in `taktus.wire`, the meaning in the process component

`taktus/wire/bpmn.py` reads and writes the XML. It knows the BPMN elements and nothing of Taktus's
processes: it turns bytes into a neutral graph of nodes, flows and lanes, and that graph into
bytes. It uses the standard library only, as every wire format does.

BPMN is a standard, not a product, so the core may name it. The process component turns the
neutral graph into a plan draft, and a process version into the neutral graph
(`process/domain/service/interchange.py`). Another interchange format would be another module
beside it, with the same two directions.

### 2. Parsing is defused

The reader drives the standard library's `expat` parser itself. A document type declaration, an
entity declaration or a reference to an external entity stops the parse, and the model is
refused with a finding that names which. Parameter entities are never parsed. A model larger
than 10 MiB is refused before it is parsed. Nothing the model refers to is read: no schema, no
import, no address.

### 3. An import yields a plan draft, never a version

Every `bpmn:process` with at least one task becomes one draft. Its parts:

- **Steps.** Every task becomes a proposed step: a step identifier derived from its name, the
  task's name and kind, and `method` empty. The step names the method kinds its kind of task
  suggests as `candidates`: a user or manual task suggests `human`; a business rule task `rule`,
  `statistics`, `ml`; a script task `rule`; a service, send or call task `worker`, `rule`,
  `llm`; a receive task and an intermediate catch event `wait`; a task of no kind every method.
  A candidate is a suggestion. The choice is the person's, in the plan dialogue.
- **Dependencies.** A step depends on the nearest steps before it, reached backwards through
  gateways and events. A flow that closes a loop is not imported. A process of Taktus is a graph
  without loops; the draft says where the loop was.
- **Gateways.** An exclusive or inclusive gateway's conditional flows become each following
  step's `condition`, in the model's own words, and a question to state it as a machine check —
  a `when` of ADR-0088. A condition Taktus itself exported (§5) is already one and is read back
  as such. A parallel gateway becomes the dependencies alone. Each gateway is listed with its
  kind, the steps before it and the steps after it.
- **Roles.** A lane becomes the role of the steps in it, under a role identifier derived from
  its name, and a question to confirm that the lane names a role, not a person. A performer
  element (`humanPerformer`, `potentialOwner`, `performer`) is not imported, and the draft says
  so.
- **Autonomy.** A draft proposes level 1, as a discovered process starts (UC-9.4).

A draft is a document of its own, with `kind: draft`. `parse_bundle` refuses it, because none of
its steps carries a method. It is never stored by the instance and never registered.

### 4. A draft becomes a bundle only through the person's answers

The person answers the draft's questions by filling in the draft: each step's `method`,
`reason` and `rejected`, its `exactness` where it produces a result, its `fallback` and `model`
where its method needs them, and its `work`. `complete` turns the filled draft into a bundle:
the role goes to a human step, or to a fallback to a person; a confirmed condition becomes the
step's `when`. Every question still open is a finding, and nothing is returned while one is. The
bundle then goes the road every bundle goes: `taktusctl bundle check`, a proposal, a rehearsal
and the person's commissioning (ADR-0091, ADR-0136 §4).

### 5. An export is a projection of a version

A process version is written as one `bpmn:process` inside a collaboration with one participant.

- Every step is a task whose kind follows its method: `human` a user task, `wait` a receive
  task, `rule` and `statistics` a business rule task, every other method a service task.
- Every dependency is a sequence flow. A parallel gateway splits where a step is followed by
  more than one step without a condition, and joins where a step depends on more than one. An
  exclusive gateway splits before the steps that carry a `when` and share their dependencies;
  each flow out of it carries the step's conditions as JSON, under the expression language
  `urn:taktus:when:1`. Where every step a join waits for carries a condition, the join is
  exclusive.
- Every role a step's `performer` names is a lane; the steps that name none are in the lane
  `Taktus`.
- Each task carries an extension element in the namespace `urn:taktus:bpmn:1` with the step's
  method, exactness class and reason; the process carries its autonomy level and version.
- The export carries a diagram (BPMN DI): steps in columns by their depth in the graph, in rows
  by lane, so that a BPMN tool can show it without laying it out.

`taktusctl bpmn export` writes the export of a bundle; `taktusctl bpmn draft` reads a model into
drafts; `taktusctl bpmn complete` turns a filled draft into a bundle. All three need no instance.

## Alternatives

- **A parsing library.** Libraries that defuse XML exist. They would be a dependency for what
  three handlers of the standard parser do: refusing a document type is stricter than expanding
  entities safely, and a process model has no need for one.
- **Importing straight into a proposal.** A proposal must pass registration (ADR-0091 §1), so
  every method would have to be guessed. A guessed method is what UC-4.1 forbids.
- **A language model choosing the methods on import.** It may help in the plan dialogue, as it
  helps any request in words (ADR-0091 §2). The import itself stays a rule: the same model gives
  the same draft.
- **The full bundle inside the BPMN extension.** The export would then round-trip losslessly,
  but two sources for one process would exist. The bundle is the source; BPMN is a projection.
- **An adapter behind a port.** A format conversion calls nothing outside. A port would add a
  seam the composition root has to wire, for a function the command line and the process
  component call directly.

## Consequences

- `taktus/wire/bpmn.py` reads and writes the format. `process/domain/model/draft.py` holds the
  draft, `process/domain/service/interchange.py` the two directions and `complete`.
- `taktusctl bpmn draft`, `taktusctl bpmn complete` and `taktusctl bpmn export`.
- No migration: a draft is never stored.

## Where this promise ends

The round trip holds for the graph, the roles and the gateways. It does not hold for the rest of
a step: the rejected alternatives, the fallback, the checks and the work are not in the export,
and an imported export is a draft again, with its methods suggested and not chosen. The bundle
stays the format that keeps a process whole.

The import reads tasks, gateways, intermediate events, lanes and sequence flows of the BPMN 2.0
process level. It does not read message flows between pools, data objects, the inside of a
sub-process, compensation or escalation semantics, or timers: a sub-process is one step, a
boundary event passes its task on, and the draft names each such element it did not import. An
event-based gateway is listed as a gateway; the waits after it are steps that wait, each with
its own question.

A role identifier is derived from a lane's name by a rule. Whether a lane names a role or a
person is decided by the person who confirms it, not by the import: no rule can tell a person's
name from a role's.

An export that a BPMN tool shows is not one Taktus runs. Changing it in that tool changes
nothing in Taktus; importing it again yields a draft.
