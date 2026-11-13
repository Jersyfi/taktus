# NTC-0278 — The evaluation platform connector is built over Langfuse's public API

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-11-13
**Raised in:** the branch `area/command3`, for DEC-0236
**How it follows:** UC-5.8 asks for the evaluation backend, prompt mirroring and cost
reconciliation through a connector over an evaluation platform's documented interface, and says
that a self-hosted platform under an open licence meets the first tier of the integration code
(`docs/architecture/contracts.md` §7). DEC-0225 and DEC-0226 prove such a connector against a
stand-in built from the product's published API, with no account. Principle 11 (European values
and sovereignty) and principle 13 (freedom instead of lock-in) favour a platform an organisation
can run itself. Of the platforms that trace, evaluate and version prompts, one that is
open-source, self-hostable and documents a public HTTP API for all three capabilities is taken.

## 1. What was decided

The first connector of the capabilities `evaluations.records`, `prompts.versions` and
`observability.costs` is built over Langfuse's public HTTP API
(`connectors/taktus_connectors/langfuse/`). It is proven against a fake of that API
(`tests/fakes/evaluation_platform_service.py`). The product's name appears only in the
connector's directory, its README, this notice and configuration; the core names the
capabilities (CLAUDE.md §6).

## 2. The evidence

- **Open and self-hostable.** Langfuse's core is published under the MIT licence and runs on an
  organisation's own servers. An organisation keeps its traces, data sets and prompts where its
  data is.
- **One documented interface for the three capabilities.** Its public API, under
  `/api/public/`, documents data sets, their items and runs, scores, prompts with versions, and
  traces with their computed cost, with HTTP basic authentication by a project's key pair.
- **Traces already reach it.** It receives OpenTelemetry over OTLP, which Taktus exports
  (ADR-0286). Its trace identifiers are the OpenTelemetry trace identifiers the ledger records,
  so a cost read there is a cost of a run's own traces.

## 3. What was considered

- **Arize Phoenix.** Open-source and self-hostable, with data sets, experiments and prompts.
  Rejected for the first connector: it does not compute and expose a trace's cost in its API,
  which cost reconciliation needs.
- **A proprietary platform (LangSmith, Braintrust, Weights & Biases).** Rejected for the first
  connector: by UC-5.8 §2 a proprietary platform meets only the second tier, and an
  organisation cannot run it itself.
- **Several platforms at once.** Rejected: UC-5.8 §3 says which platforms have a connector is a
  matter of what exists; one connector proves the capabilities, and another is an addition behind
  the same capabilities.

## 4. Which entry permits it

M2.6. The owner may overrule it in the pull request.

## 5. The entry it proposes

None beyond M2.6: which product a connector is built over is a choice of what exists (UC-5.8
§3), and the first of a capability follows the order above — open-source and self-hostable
first.
