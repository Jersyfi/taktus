# Events contract v1

An **event** is something that happened in a tool the organisation works in: an issue was opened
or labelled, a pipeline completed, a branch was pushed, a message mentioned Taktus. This
contract says which events exist, what each carries, and how a process version declares that an
event starts it. How an event is delivered once and only once to the processes it starts is
ADR-0048.

| File | Contents |
|---|---|
| [`Event.json`](Event.json) | the event, the catalogue of kinds with the context each requires, the filter, the condition and the event trigger, as JSON Schema 2020-12 |
| [`examples/`](examples/) | valid and must-fail examples per definition |

`make gate-contracts` checks the schema and every example. The contract has no conformance
suite of its own: the connector that produces an event is held by the connector suite (C-07),
and the core's binding of these shapes is held to this schema by `tests/contract` from the
change that builds event reactions (issue #76).

---

## 1. Where an event comes from

An event is derived from an **intake** — a delivery a connector verified and normalised
(`contracts/connector/v1` §7) — whose sender the identity component placed in a tenant
(control-plane.md §2). An intake whose sender nobody could place is kept nowhere, so it never
becomes an event.

The event keeps what a trigger needs and nothing else:

| Field | What it is |
|---|---|
| `id` | the source system's identifier for the delivery, the intake's `event_id`; a redelivery carries the same one |
| `kind` | one kind of the catalogue (§2) |
| `channel` | the capability of the channel it arrived on, such as `channel.repo` |
| `occurred_at` | when the source says it happened |
| `received_at` | when the intake received it |
| `context` | what it concerns, as identifiers the source gave: strings, flags and lists of strings |

**An event carries no sender, no text and no credential.** Who caused it is the command's, which
the event is completed into (§5). What was written is the intake's. A trigger therefore cannot
start a process because of who someone is or what they wrote.

## 2. The catalogue

A **kind** names the subject, singular, a dot, and what happened to it. v1 has eight. A
connector that serves a channel normalises its deliveries into these kinds and fills at least the
fields each requires; it may add fields of its own.

| Kind | Context it requires | What happened |
|---|---|---|
| `issue.opened` | `repository`, `issue` | an issue was opened |
| `issue.labelled` | `repository`, `issue`, `label` | a label was added to an issue; one event per label |
| `issue_comment.created` | `repository`, `issue`, `comment`, `is_pull_request` | a comment was written on an issue or a pull request |
| `pull_request.opened` | `repository`, `pull_request`, `head`, `base` | a pull request was opened |
| `pipeline_run.completed` | `repository`, `run`, `conclusion`, `head`; `pull_request` where there is one | a pipeline run ended, with its conclusion |
| `branch.pushed` | `repository`, `branch`, `head`, `paths` | commits were pushed to a branch; `paths` lists the files they changed, as far as the source lists them |
| `message.posted` | `conversation`, `message`; `thread` where there is one | a message was posted in a conversation |
| `message.mentioned` | `conversation`, `message`; `thread` where there is one | a message mentioned Taktus |

A kind outside the catalogue is not an event of v1. A connector may still accept it as an
intake, and a person may still complete that intake into a command by hand; no trigger can name
it. A new kind is a later version of this contract, never a connector's own addition.

**What the blueprint's earlier names became.** `blueprints/dev-orchestration/blueprint.yaml`
named events before this contract existed. `issue.ready` is `issue.labelled` with the filter
`label: ready`. `roadmap.changed` is `branch.pushed` with the filter `branch: main` and
`paths: docs/roadmap.md`. `pullrequest.opened` is `pull_request.opened`. `chat.mention` is
`message.mentioned`. `discussion.created`, `merge`, `anchor.hit` and `milestone.reached` are not
in v1: the first two have no connector that would deliver them, and the last two happen inside
Taktus, not in a tool.

## 3. The event trigger

A process version declares in `triggers` what starts it. A trigger names either a schedule
(ADR-0035) or an event. An event trigger is `EventTrigger`:

```yaml
triggers:
  - event: issue.labelled
    filter: { label: ready }
    condition: capacity.available
    inputs: { records_path: docs/decisions/open }
    from_event: { issue: issue }
```

| Field | Required | What it says |
|---|---|---|
| `event` | yes | the kind it reacts to |
| `filter` | no | which events of that kind it takes (§4); without it, every one |
| `condition` | no | what must hold on the instance before the run starts (§4) |
| `inputs` | no | fixed values for the run's inputs, by name |
| `from_event` | no | inputs taken from the event: input name to context field |

**Every input the process declares is given**, by `inputs` or by `from_event`, or the version is
refused when it is registered. A run started by an event has nobody to ask, as a run started by
a schedule has nobody (ADR-0035 §5). `from_event` may name only a field the kind requires, so
that a run never starts with an input missing. A context field is given as the event carries
it: a string, a flag, or a list of strings. Where the input's declared example is an integer, a
string of decimal digits is given as that integer, so that an issue's number reaches an
operation that reads a number.

Registration refuses, with every finding at once: a kind outside the catalogue, a filter field
the kind does not carry, a condition outside §4's list, an input given twice or not at all, and
an input the process does not declare.

## 4. How a trigger decides, and by which method

**The filter is a rule over the event alone.** Every entry must hold. An entry names a context
field and a value, or a list of values. It holds when the field's value equals one of them. For
a field whose value is a list, such as `paths`, it holds when any element equals one of them. A
field the event does not carry makes the entry fail.

```yaml
filter: { label: ready }                                   # the label added is `ready`
filter: { branch: main, paths: docs/roadmap.md }           # pushed to main, touching the roadmap
filter: { conclusion: [failure, timed_out] }               # a pipeline that did not pass
```

Nothing but the event is read: no source system, no clock, no other state, and no model. The
same event and the same version give the same answer, every time. **Whether a run starts is
never decided by a probabilistic method**, as an emergency stop is not (ADR-0023). A process
that must judge whether there is anything to do — whether an issue lacks a section, whether a
comment asks for something — does it in its first step, with that step's method, reason and
fallback, like any step. That step ends the run when there is nothing to do. A trigger is not a
step, so it carries no method choice of its own: its method is `rule`, fixed by this contract.

**The condition is a named state of the instance**, checked when the reaction would start the
run. A condition that does not hold makes the reaction wait: it is tried again on the next pass,
and the event is not discarded. v1 names one:

| Condition | Holds when |
|---|---|
| `capacity.available` | the instance's admission against its platform (`docs/architecture/platform.md`) would admit the run's work now: the state's storage, and, where a step of the version is a worker step, the memory of one execution unit as the instance launches it; a quantity the platform does not observe is no refusal, as in the admission itself |

A filter decides whether an event is for this trigger; it is answered once. A condition decides
when the run may start; it is answered again until it holds.

## 5. What an event starts

Each event is matched against the triggers of every process's active version in the tenant it
was placed in. The process component answers which triggers match; the automation role starts
the runs. ADR-0048 states how, and what holds when the instance restarts in between:

- An event that matches no trigger starts nothing. Its intake stays as it was, and a person may
  still complete it into a command by hand.
- An event that matches triggers of one or more processes is completed into one command, which
  acts for the identity its sender was placed as. One run of each such process is started from
  it, with the inputs of the first trigger of that process that matched, in the order the
  version declares them.
- One delivery starts each process at most once, however often it is delivered and whichever
  instance reacts.
- Every run an event started carries `run.triggered` in the ledger, with the digest of the
  trigger and the event — never their content (ADR-0006).

## 6. Versioning

The schema's `$id` is its path under `https://taktus.eu/contracts/` (ADR-0019). Until a version
of Taktus that uses this contract is released, v1 may still move. A new kind or a new condition
is added to v1 and breaks nothing; removing one, or changing what a kind requires, is a v2.
