# Changes contract v1

A **change** is a change of state of a run, a step or a decision request, as the ledger recorded
it. A reader opens one long-lived response, `GET /changes` on the `api` role, and receives the
changes on it as they are recorded. How they are read, resumed and kept to what the reader may
see is ADR-0055; this contract is the shape of what the reader receives.

| File | Contents |
|---|---|
| [`Changes.json`](Changes.json) | the snapshot, the change, the scope, the position, the kinds sent and the states, as JSON Schema 2020-12 |
| [`examples/`](examples/) | valid and must-fail examples per definition |

`make gate-contracts` checks the schema and every example. `tests/contract/test_changes_binding.py`
holds the core's binding to it: the kinds and the states are the run's and the decision
component's, and every example passes through the binding or is refused by it.

---

## 1. The format

The response is `text/event-stream`: Server-Sent Events, a standard text format over plain HTTP.
Every event has a type, an `id` and one line of `data`, a JSON document:

```
retry: 1000

event: snapshot
id: sha256:a1…
data: {"position":"sha256:a1…","scope":{"kind":"tenant"},"runs":[…]}

event: change
id: sha256:b2…
data: {"position":"sha256:b2…","run":"run_01","step":"classify","kind":"step.finished",…}

: heartbeat
```

| Event | When | Shape |
|---|---|---|
| `snapshot` | first, and again after a long absence (§3) | `#/$defs/Snapshot` |
| `change` | once for every ledger entry of a kind of `#/$defs/Kind` in the scope that the reader may see | `#/$defs/Change` |
| heartbeat | a comment line every 15 seconds, from the opening of the stream, whatever happens | none |

`retry: 1000` asks the reader to wait one second before it reconnects.

## 2. What a change carries

The run, the step and the decision request it concerns, where the entry names them; the
entry's kind and outcome token; the method kind of the step; when it was recorded; whether it
belongs to a rehearsal; and `state`, the state the entry led to — of the run, the step or the
decision request, each only where the entry changed it. Which state a kind and an outcome lead
to is published beside the state machine that owns it: the run component
(`components/run/domain/model/recorded.py`) and the decision component
(`components/decision/domain/model/recorded.py`). A representation reads the state from the
change and never derives it a second time.

**A change carries no content, no figure and no person.** The entry's actor, its consumption,
its model, its adapter and its digest are left out. What a run has consumed is read from the
component that owns it; a result through the ordinary requests, under their own rules.

## 3. Positions and resuming

A **position** is the hash of a ledger entry: the `id` of every event, and `position` in its
data. It is not the sequence number, which counts every entry of the tenant: two positions
would then say how many changes were withheld between them.

A reader that reconnects, to any replica, sends the last position it received as the header
`Last-Event-ID`. It receives every change after it, in the ledger's order. When the position is
unknown in the tenant, or more than 1,000 entries of the tenant lie behind it, it receives a
fresh `snapshot` instead, and the changes from there. A snapshot replaces what happened in
between; it does not replay it.

## 4. Scope and visibility

`?process=<id>` limits the stream to the runs of one process, `?run=<id>` to one run; neither
is the tenant of the reader's identity. A run the reader may not see is absent: not listed in a
snapshot, never sent as a change, not replaced by anything that could be counted. Which runs a
reader may see is one predicate of the reporting component, asked for each change when it is
sent. Until the role-based views of UC-6.4 exist, it is the tenant boundary.

The account key is read from `Authorization: Bearer` and from nowhere else. A stream whose key
no longer proves an identity ends at its next change or heartbeat.
