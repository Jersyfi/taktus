# Contracts

The boundary between what Taktus builds and what it conducts.

---

## 1. Three adapter families

| Contract | For | Basis | Directory |
|---|---|---|---|
| **Worker** | execution units: coding agents, agent runtimes, script runners, training runs | HTTP + Server-Sent Events, JSON Schema | `contracts/worker/v1` |
| **Connector** | tools and channels: repositories, ticket systems, chat, knowledge, warehouses | MCP | `contracts/connector/v1` |
| **Model** | models | OpenAI-compatible endpoints | `contracts/model/v1` |
| *(Process)* | the portable process bundle — a format, not an adapter | JSON Schema | `contracts/process/v1` |
| *(Shared kernel)* | the concepts all of the above share — a vocabulary, not an adapter | JSON Schema | `contracts/shared/v1` |

HTTP and SSE rather than gRPC for workers: a worker must be buildable without knowing the core's
language — as a script, as a small service, as a shell wrapper around a foreign CLI. Efficiency is
not the bottleneck here; adapter variety is.

---

## 2. The contracts in brief

### 2.1 Worker

| Capability | Why it is required |
|---|---|
| **Accept an assignment** — task, context, frame, autonomy level | governance reaches into execution |
| **Stream events** — progress, decisions, tool calls | ledger and status queries |
| **Report consumption per step** — tokens, compute seconds, resource class | accounting in normalised units |
| **Estimate demand before starting** and **signal step boundaries** | admission control; stopping without data loss |
| **Hand over artifacts** — code, documents, structured data, model files | a result is data, not prose |
| **Accept credentials at runtime, never store them** | secret safety |
| **Least privilege** — only the tools the process allows | permission model |
| **Declare capabilities** — what this worker can do, and optionally its own version | processes reference capabilities, never product names; the version is recorded in the provenance of every result (ADR-0021) |

Full specification: [`contracts/worker/v1/README.md`](../../contracts/worker/v1/README.md).
The core's side of it is the worker port (`src/taktus/ports/worker.py`): the contract's shapes
as frozen types and the protocol the run component calls. `tests/contract` holds those types to
`Worker.json` and its examples, so that the port and the contract cannot drift apart.

### 2.2 Connector

A connector is an MCP server; the contract is what Taktus needs on top of MCP (ADR-0024). Two
directions, governed differently: **actions**, where Taktus calls an operation, and **intake**,
where an event from the outside becomes a command or is refused.

| Capability | Why it is required |
|---|---|
| **Declare capabilities and operations** — by function, never by product; served as one MCP resource | processes bind capabilities; the tool list is checked against the declaration |
| **Declare the effect of every operation** — `read`, `write`, `delivery` | `write` and `delivery` leave the system: the run records them as egress entries, and correcting their result afterwards is anchored (ADR-0022). Declared, "has left the system" is a field, not a judgement |
| **Declare the idempotency of every outward operation** — `native`, `marked`, `none` — and honour the idempotency key of every call | a step retried after a restart must not open a second pull request (ADR-0005). `none` is allowed and honest: Taktus then never repeats the call on its own |
| **Act with the requesting identity's credentials, by name, read at the call** | source-system permissions remain in force; the connector has no credential of its own |
| **Classify every error** — a failure with cause, effect and retryable | the run knows whether the effect happened and whether the same call may be repeated (ADR-0021) |
| **Report consumption per call** | connector calls cost close to nothing and are counted, not ignored |
| **Verify the signature of every incoming event before reading it**, then normalise it as far as the channel can | intake without a signature is not a valid declaration; the identity component completes the command |

Full specification: [`contracts/connector/v1/README.md`](../../contracts/connector/v1/README.md).
The connector port on the core's side exists for the intake direction (`src/taktus/ports/
connector.py`, over MCP in `adapters/driven/connectors/mcp/`): the HTTP surface hands a webhook
delivery to the connector that serves the channel and keeps what it accepted. The action
direction, and the run's binding of connector steps — writing the egress entry from the
result, halting instead of retrying an outward operation with `idempotency: none` whose outcome
is unknown — arrive with `0.2.0`.

---

## 3. Conformance and maturity

Every adapter tests itself:

```
uv run taktusctl conformance run --contract worker/v1 --endpoint http://localhost:9000
uv run taktusctl conformance run --contract connector/v1 --endpoint http://localhost:9100/mcp \
    --scenario scenario.json
```

(`taktusctl` lives in the project environment, hence `uv run`.)

| Maturity | Condition |
|---|---|
| **experimental** | from the community, no evidence |
| **verified** | conformance suite passed **and** removal test passed |
| **reference** | maintained by the project, the model for new adapters |

**Production processes at autonomy level 3 and above may only use adapters at *verified* or above.**

The conformance suite is the real asset here — not the adapter code, but the ability to check.
Without it, "interchangeable" is an assertion.

The suite lives in `src/taktus/conformance/` and imports nothing from the control plane; it talks
to a worker over HTTP and SSE, and to a connector over MCP, as a foreign control plane would. It
runs W-01 to W-11 and W-13 against a live worker and C-01 to C-09 against a live connector, and reports
W-12 and C-10, the removal test, as *pending* until processes exist to remove an adapter from.
Its report states which half of *verified* it proves. What both halves share — the report, the
findings, the catalogue of checks, the schema validators — lives at the package level; the
connector half is `src/taktus/conformance/connector/`. How a third party runs it against an
adapter of their own: [`contracts/worker/v1/CONFORMANCE.md`](../../contracts/worker/v1/CONFORMANCE.md)
and [`contracts/connector/v1/CONFORMANCE.md`](../../contracts/connector/v1/CONFORMANCE.md).
`make gate-conformance` proves the suite itself for both contracts: the reference worker passes
it in both profiles, the reference connector passes it against a fake of its service, and for
every fault either reference adapter can inject the suite fails on exactly that check.

Before the suite runs against an adapter, `make gate-contracts` checks the contract itself: every
schema is valid and carries the `$id` its path prescribes, every example validates, and every check
W-01..W-13 and C-01..C-10 has a fixture (`tools/validate_contracts.py`).

Every schema is identified by `https://taktus.eu/contracts/<family>/v1/<Concept>.json` — its path
under `contracts/` behind the project's domain. A released v1 schema is immutable; changes become
v2 (ADR-0019).

---

## 4. Reference adapters

Under `workers/`, `src/taktus/adapters/driven/connectors/` and `.../models/`. They are proof and
example, not a requirement. The core runs with all of them removed — it simply cannot reach anything.

| Family | Adapter | Why this one |
|---|---|---|
| Worker | `script` | the trivial worker. **Mandatory from day one:** a contract a shell script cannot satisfy is built around one specific coding agent. Exists (`workers/script/`), passes the suite; its `longrun` profile has the shape of the second proof case and trains nothing. The control plane reaches it through the HTTP worker adapter (`src/taktus/adapters/driven/workers/http/`), the client side of this contract; `examples/processes/` runs a process against it. |
| Worker | `mlbench` | training, evaluation, embeddings, classical ML. The second proof case: hours of runtime, a GPU held, a model artifact returned. |
| Worker | `claudecode` | the first real coding worker |
| Worker | `codex` | the second real coding worker; validates the contract against a second vendor |
| Connector | `github` | repository: issues, pull requests, pipelines, comments — actions and webhook intake. Exists (`src/taktus/adapters/driven/connectors/github/`), passes the suite against a fake of its service; the example of idempotency: a pull request opened for a step is opened once, proven across a restart of the connector. Reached by the daemon's webhook intake; its operations are not yet bound into the run (`0.2.0`) |
| Connector | `chat` | both a command channel and a delivery channel |
| Connector | `http` | the generic fallback for anything with a documented API |
| Model | `openai_compatible` | covers Ollama, vLLM and most vendors |
| Model | `anthropic` | native capabilities the common denominator does not carry |

**Rule:** a second real worker of each shape exists **before** features build on worker behaviour.
Otherwise there is a contract with one implementation, and that is not a contract.

---

## 5. What Taktus does not ship

Taktus bundles no foreign CLIs, no foreign clients, no foreign runtimes. It ships the contract, the
check and the references. Anything else would be the tool landscape Taktus explicitly is not.

---

## 6. Where adapters live

**Until `1.0.0`:** all in the main repository, because the contract still moves and separate
repositories would mean a version matrix instead of progress.

**From `1.0.0`:** the contract is frozen and versioned. Community adapters move to their own
repositories; the main one keeps the references and the suite. See
[ADR-0009](../adr/ADR-0009-adapter-monorepo.md).

---

## 7. Integration code

Two tiers, because core dependencies and customer tools need different standards.

**Tier 1 — what Taktus itself needs to run** (database, queue, secret store, telemetry, reference
workers): an open contract · an OSI-conforming licence · self-hostable · data exportable · removal
test passed · an active community or a named replacement.

**Tier 2 — what Taktus conducts:** liberal. Taktus orchestrates what the organisation already has,
including proprietary systems. Condition: connected through the connector contract, source-system
permissions remain in force, no circumvention.

**Excluded outright in both tiers:** tools with a surveillance character towards individuals
(keystroke logging, productivity scoring, location tracking) · tools that bypass source-system
permissions · tools with no data export for Taktus's own data.
