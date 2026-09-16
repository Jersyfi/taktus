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

## 2. The worker contract in brief

| Capability | Why it is required |
|---|---|
| **Accept an assignment** — task, context, frame, autonomy level | governance reaches into execution |
| **Stream events** — progress, decisions, tool calls | ledger and status queries |
| **Report consumption per step** — tokens, compute seconds, resource class | accounting in normalised units |
| **Estimate demand before starting** and **signal step boundaries** | admission control; stopping without data loss |
| **Hand over artifacts** — code, documents, structured data, model files | a result is data, not prose |
| **Accept credentials at runtime, never store them** | secret safety |
| **Least privilege** — only the tools the process allows | permission model |
| **Declare capabilities** — what this worker can do | processes reference capabilities, never product names |

Full specification: [`contracts/worker/v1/README.md`](../../contracts/worker/v1/README.md).
The core's side of it is the worker port (`src/taktus/ports/worker.py`): the contract's shapes
as frozen types and the protocol the run component calls. `tests/contract` holds those types to
`Worker.json` and its examples, so that the port and the contract cannot drift apart.

---

## 3. Conformance and maturity

Every adapter tests itself:

```
uv run taktusctl conformance run --contract worker/v1 --endpoint http://localhost:9000
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
to a worker over HTTP and SSE as a foreign control plane would. It runs W-01 to W-11 against a
live endpoint and reports W-12, the removal test, as *pending* until processes exist to remove an
adapter from. Its report states which half of *verified* it proves. How a third party runs it
against a worker of their own: [`contracts/worker/v1/CONFORMANCE.md`](../../contracts/worker/v1/CONFORMANCE.md).
`make gate-conformance` proves the suite itself: the reference worker passes it in both profiles,
and for every fault the reference worker can inject the suite fails on exactly that check.

Before the suite runs against a worker, `make gate-contracts` checks the contract itself: every
schema is valid and carries the `$id` its path prescribes, every example validates, and every check
W-01..W-12 has a fixture (`tools/validate_contracts.py`).

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
| Connector | `github` | repository, issues, pull requests, pipelines |
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
