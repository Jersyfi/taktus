# ADR-0262 — A warehouse connection reads until a person grants writing, and every query is recorded

**Status:** accepted · extends ADR-0213, ADR-0024, ADR-0014, ADR-0006, ADR-0109 · uses ADR-0264 ·
UC-5.6 §2 · DEC-0228

## Context

UC-5.6 connects Taktus to the warehouse where an organisation keeps its consolidated data.
ADR-0213 gave it one capability, `warehouse.queries`, with one operation that only reads. UC-5.6
§2 asks for six things beyond that:

1. A new connection reads only. Writing is a grant on that connection, made by a person with the
   right to make it, and recorded. A write without the grant is refused before it reaches the
   warehouse.
2. Every query Taktus sends is recorded with the step that sent it, by reference in the ledger,
   and a person entitled to the step can read the query text.
3. The warehouse is asked with the identity Taktus acts for, so that its row-level and
   column-level security apply. ADR-0264 built that for every connector step.
4. A figure that feeds a step of class `exact` comes from a query fixed in the process version.
   A query a language model writes may feed only a step of class `tolerant` or `free`.
5. A threshold over a warehouse figure can start or escalate a process, with the reading in the
   step's provenance record.
6. Every warehouse figure in a view or a report is in the export (UC-5.7).

A **connection** here is what an instance configures for one capability: one entry of
`TAKTUS_CONNECTORS`, serving every tenant of the instance. A **querying capability** is one
whose reading runs a statement in a query language and computes its answer from it. A **grant**
is a tenant's record that a person allowed the writes of one connection.

## Decision

### 1. The warehouse may be written, by one operation

The connector of `warehouse.queries` gains `warehouse.queries.change`: one statement that
changes data — `INSERT`, `UPDATE`, `DELETE` or `MERGE` — over the configured dataset. Its effect
is `write`, its idempotency `marked`. The statement must begin with one of those four words, and
the warehouse's own dry run must call it one of them; otherwise nothing runs. It is run as a
job whose identifier is derived from the call's idempotency key. A repeat of the call finds the
job of that identifier, reads it, and reports `replayed`. A write asks the token for the scope
that may write; a reading keeps the read-only scope.

### 2. A connection of the warehouse reads until a person grants writing

The capabilities whose connection reads until a grant are listed once, in the connector port
(`READ_UNLESS_GRANTED`): `warehouse.queries`. For an operation of such a capability that acts
outward, the run engine asks for a grant in force before anything else of the call — before the
message gate, the booking of the call and a rehearsal's replay. Without one the step fails with
outcome `write not granted`. It is not retried; its fallback applies. The connector is never
called.

A grant is the governance component's record `ConnectionGrant`, one per tenant and capability.
It is made, and withdrawn, only by a person: an identity the tenant knows, acting through the
surface with its own key, never a run and never a worker. The right to make it is held by the
role `owner`. The ledger records a grant as `connection.granted` and a withdrawal as
`connection.withdrawn`, each with the person as actor and the record's digest. A refused attempt
is `connection.refused`, with the reason as outcome: `process`, `worker`, `unknown` or `role`.
The surface is `GET`, `PUT` and `DELETE /connections/{capability}/grant`.

### 3. Every query is recorded by reference, and read where its run is read

For every operation of a querying capability — listed once, in the connector port
(`QUERYING`): `warehouse.queries` — the run engine stores the request as sent, the operation and
its input, in the object store before the call. The ledger records `query.sent` with the run and
the step that sent it and the request's digest. The ledger holds no query text (ADR-0006). A
query that the warehouse then refuses is recorded too.

`GET /levels/runs/{run_id}/steps/{step_id}/queries` answers the queries the step sent, each with
its text, its parameters, its operation and when it was sent. It answers a reader who may see
the run, by the rule that decides who sees a run (ADR-0063); anyone else gets the answer for a
run that does not exist.

### 4. Which queries may feed an exact step

A registration rule of the process component holds every reading of a querying capability in a
version to where its figures may go. Data flows from step to step through `$from` references.

- A reading is **model-written** when its input refers, directly or through other steps, to the
  result of a step on a language model, a neural method or a worker. Neither its result nor that
  of any step that refers to it, directly or through other steps, may be of class `exact` or
  `sourced`.
- A reading is **fixed** when its `query` is literal text in the version. A step of class
  `exact` that refers to a reading, directly or through other steps, refers only to fixed ones.

A version that breaks either is refused at registration, with every finding at once.
Registering it is the review: the query is part of the version a person registered.

### 5. A warehouse figure is a signal's value

A corridor (ADR-0109) reads its number from a step's result. A warehouse answers every value as
text. A corridor therefore reads a text that is a decimal number as that number. A corridor over
a fixed warehouse reading escalates at once when red: the incident names the run and the step,
and that step's provenance record holds the reading by its digest and the moment it was read.
The daily report offers the processes a person may start from it, as for every signal.

## Alternatives

- **A grant per operation, or per statement.** UC-5.6 grants per connection. A finer grant can
  later sit in the same record.
- **The grant as instance configuration.** The operator's configuration has no person behind it
  and no ledger entry. UC-5.6 asks for a person with the right, recorded.
- **Every connection reads until granted.** Every process that writes today — a deployment, a
  chat message — would stop at once. UC-5.6 names the warehouse; the list can grow.
- **The query in the provenance record's reference only.** That reference is cut at 200
  characters and is not the ledger. The object store keeps the whole request; the ledger points
  at it.
- **A connector field that marks a querying operation.** The connector contract allows no such
  field. A change of the contract for one capability weighs more than one list in the port.
- **Figures as numbers in the connector's answer.** A warehouse's integers and decimals exceed a
  float; the connector keeps the text it was given (ADR-0213), and the corridor reads it.

## Consequences

- `connectors/taktus_connectors/bigquery/`: `warehouse.queries.change`; the fake
  `tests/fakes/warehouse_service.py` runs jobs, refuses a duplicate job as the API does, and
  limits rows and columns per service account.
- `src/taktus/ports/connector.py`: `READ_UNLESS_GRANTED` and `QUERYING`.
- `src/taktus/components/governance/`: `ConnectionGrant` and `ConnectionGrants`.
- `src/taktus/components/run/`: the port `WriteGrants`, the refusal before the call, and
  `query.sent`.
- `src/taktus/components/process/domain/service/queries.py`: the registration rule.
- `src/taktus/components/reporting/`: `StepQueries`, and the corridor's decimal text.
- `src/taktus/adapters/driving/rest/`: the grant and the queries of a step.
- `blueprints/software-operations/processes/B-9.02-figures.yaml`: the model-written reading and
  what it feeds become `tolerant`, and the reading is made on behalf of the person who asked.

## Where this promise ends

- **The warehouse's own rights are the last wall.** A grant lets Taktus send a write. Whether
  the credential may write, and what, is decided in the warehouse (UC-5.6 §3).
- **The lists name one capability.** Another querying capability, or another connection that
  should read until granted, is added to the list in the port by an ADR.
- **A query written by a person is not a model's.** A query given as a run's input may feed a
  step of class `sourced`. It is not fixed, so it feeds no step of class `exact`.
- **A model's influence is followed through references only.** A model that shapes a query by
  another path — a text a person copies into the version — is not seen.
- **The owner holds the right.** A tenant cannot yet give the right to grant to another role.
- **The export of the figures is not built.** UC-5.7, on which the sixth requirement rests, is
  specified only. Until it is built, a warehouse figure in a view or a report is in no export.
- **A grant is not time-bound.** It stays in force until a person withdraws it.
