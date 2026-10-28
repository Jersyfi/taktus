# ADR-0144 — A worker's outward calls and model answers count in the stop to repetition

**Status:** accepted · extends ADR-0132 (the stop to repetition) with what ADR-0139 §5 made a worker report · issue #433

## Context

ADR-0132 stops a step that repeats itself. It counts what the engine itself calls: outward
connector calls and the answers of its own language models. A worker's calls happen inside its
assignment, and ADR-0132 left them uncounted, because the worker contract did not say whether
a tool call acts outward and reported no model call at all.

ADR-0139 §5 closed that gap in the contract. A `tool.called` event may carry `effect`, `local`
or `outward`. A new event, `model.called`, reports each answer of a language model the worker
received inside a step. Both are optional, and both are the worker's own statements.

One difference to the engine's own calls stays. The engine decides before it calls. A worker
reports a call after it made it. The rule can therefore not prevent the call that crosses the
limit. It can stop the work at the next point where a stop takes effect.

Two words are used below. A **boundary** is the point a worker's `step.boundary` event marks:
the step's result so far is kept, and a stop takes effect there (ADR-0005). A **tool result**
is the answer a tool call gives the worker: the next model answer has something new before it.

## Decision

### 1. A worker's reports are recorded in the run's ledger as the engine's own

While the run reads a worker's stream, it records:

- **`connector.called`** for every `tool.called` with `effect: outward` that was not refused.
  The identity is the tool and the `arguments_digest` the worker reported. The shape is the
  engine's own (ADR-0132 §4), so a worker's call and an engine's call with the same identity
  count together.
- **`model.called`** for every `model.called` event, against the run's step.
- **`tool.result`**, outcome `returned`, for the first tool call that was not refused after a
  model's answer. A local call, an outward one and one that says nothing of its effect are
  all tool results. Further tool calls before the next answer record nothing more.

A refused call was not made, and records nothing. A call without `effect` is never counted as
outward: the worker said nothing about what it acts on.

### 2. The rule counts the same entries, and stops at the worker's next boundary

The count of a call's identity is the number of its `connector.called` entries in the run. The
count of a step's model answers is the number of its `model.called` entries since its last
`tool.result`. The engine's own model steps record no tool result, so for them every answer in
the run counts, as ADR-0132 §5 says.

When a count becomes larger than the tenant's limit, the rule fires once for the assignment:

- `repetition.stopped` records the facts by digest: the rule, the action, the count and the
  limit. The action is the tool, or `worker <adapter>` for model answers.
- The governance component raises the incident of kind `step.repeated`, as ADR-0132 §5 says.
- The worker is asked to stop at its next boundary.

When the assignment then ends `stopped`, the step is `stopped` with its checkpoint. Its reason
names the action, the count and the limit. The run halts with cause `repeated`.

### 3. A resume continues from the checkpoint, and the counts persist

A resume hands the step to its worker again from its checkpoint. The counts are read from the
ledger, so the next call of the same identity, or the next answer without a tool result,
crosses the limit again. The step is stopped again, until a person raises the tenant's limit.
The rule stops; a person decides what happens next (ADR-0023).

### 4. The stop is a rule

| Check | Method | Reason | Rejected |
|---|---|---|---|
| the stop to a worker's repetition | `rule` | the same reports must stop the same step every time, and a person must be able to check it from the ledger (ADR-0023) | `llm` — a model that judges whether an agent is looping decides differently each time; a count kept in the engine's memory — lost at every restart, and not checkable afterwards (ADR-0006) |

The decision is `exact` and is not a result of the process.

## Alternatives

- **Rejecting the step, as for an engine step.** ADR-0132 rejects an engine step before its
  call, and nothing of it ran. A worker's step has run up to a boundary, and its result so far
  is kept there. Rejecting it would throw that away. It stops with its checkpoint instead.
- **Stopping at once, without a boundary.** A stop outside a boundary loses the work since the
  last one (ADR-0005). The worker stops at its next boundary.
- **Stopping when the count reaches the limit.** The engine stops before the call that would
  cross. For a worker that would stop a step that made exactly as many calls as the limit
  allows and would then have finished. The rule fires once the limit was crossed.
- **Counting every tool call.** A coding agent reads the same file many times on purpose
  (ADR-0132, *Alternatives*). Only calls the worker marks `outward` count.
- **Recording every tool call.** A tool result after a model's answer is enough to reset the
  count. One entry per answer bounds what the ledger receives.

## Consequences

- The run's domain service `repetition` gains `reported`, `TOOL_RESULT` and `Watch`, the rule
  over a worker's stream; `answers` counts since the step's last tool result.
- `RunEngine._follow` records the entries of §1 and applies the rule as the events arrive.
- The ledger kind `tool.result`.
- A step stopped by the rule at a worker's boundary halts its run with cause `repeated`.
- The fake worker reports tool calls and model answers per inner step (`acts`).

## Where this promise ends

The rule counts what the worker reports. A worker that marks no call `outward`, or reports no
model answer, is not counted, and the conformance suite cannot check that it reports every one
(ADR-0139, *Where this promise ends*). Two calls with the same tool and the same argument digest
count as one identity even where the target system would treat them differently. A worker
computes the digest of its arguments itself; two workers that compute it differently never
count together.

The worker reports a call after it made it. The call that crosses the limit has been made, and
the worker may make more calls before it reaches its next boundary. An assignment that ends
before a boundary keeps its end: a step that succeeds is not undone, and its incident stands.

The counts persist in the ledger as events arrive. An instance that dies between two
boundaries is followed by one that reads the stream again from the last boundary. The calls
reported since then are recorded a second time. The count is then too high, and the step stops
sooner, never later. The limit counts within one run; a loop across runs is not seen.
