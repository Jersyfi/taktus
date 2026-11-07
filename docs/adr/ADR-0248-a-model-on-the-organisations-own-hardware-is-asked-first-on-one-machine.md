# ADR-0248 — A model on the organisation's own hardware is asked first on one machine

**Status:** accepted · extends ADR-0116 (purpose chains and locations), ADR-0136 (the
one-machine installation) and `contracts/model/v1` · UC-8.1, UC-8.3, UC-11.1 · DEC-0225, DEC-0226,
DEC-0228

## Context

UC-8.3 asks that Taktus run with no outside model provider at all. For an individual or a small
organisation, every purpose is bound to a local model by default, and an outside provider is an
explicit setting with its location declared. UC-8.1 asks that one process run against a model
on the organisation's own hardware and against a remote provider, by configuration alone.

The model port has one adapter. It speaks the chat-completions dialect (`POST
{endpoint}/chat/completions`). The servers that run open models on one's own machine speak the
same dialect: the most widely used of them documents `/v1/chat/completions` and `/v1/models`
at port 11434 (docs.ollama.com, *OpenAI compatibility*), and vLLM's and llama.cpp's servers
document the same two paths. Every configured model already declares where it processes
data: `own`, `eu` or `elsewhere` (ADR-0116 §2). A tenant's residency rule `own` already keeps
every step on models declared `own`.

Two things were missing. The one-machine installation bound no model at all until the operator
named one. A local server, which usually serves the one model it was started with, also had to
be told that model's name.

The project's own provider is Anthropic only (DEC-0225). Any other provider is proven against a
stand-in of its published interface (DEC-0226). A local server is proven the same way.

## Decision

### 1. A local server is a model like any other

A model server on the organisation's own hardware is reached through the one adapter and the
model contract, declared `TAKTUS_MODEL_LOCATION=own` and usually `TAKTUS_MODEL_BILLING=
per_hardware_time`. Nothing in the core names a server. A process names a purpose, and the
configuration decides whether a local or a remote model serves it.

### 2. Configured without a name, the adapter asks the server for its one model

The adapter configured with no model name asks `GET {endpoint}/models` once, before its first
completion. It then asks for the one model listed there. A server that lists none, or several,
is a model error that names them and the setting `TAKTUS_MODEL_NAME`. Settings still refuse an
endpoint without a name, except in §3.

### 3. Local first, on one machine

`TAKTUS_MODEL_LOCAL_FIRST=true` is the setting of the configuration offered to an individual or
a small organisation. `deploy/docker/compose.yml` sets it by default. With it:

- **no model named**: every purpose is bound to the model server at
  `TAKTUS_MODEL_LOCAL_ENDPOINT`, default `http://host.docker.internal:11434/v1`, declared `own`
  and billed `per_hardware_time`, with its model asked of the server (§2);
- **a model named in its place** (`TAKTUS_MODEL_ENDPOINT`) must declare
  `TAKTUS_MODEL_LOCATION`. Without it the instance does not start, and says so. An outside
  provider is then a deliberate setting with its location stated.

Without the setting nothing changes. A cluster's chart does not set it.

### 4. The outside route is closed by the residency rule

An installation that must not reach an outside provider sets its tenant's residency rule to
`own` (`taktusctl residency set --location own`). Every model not declared `own` is then passed
over on every route, with the reason `residency` in the provenance. No step reaches it, even
when it is configured.

### 5. A second dialect, and providers proven against their published interfaces

`TAKTUS_MODEL_DIALECT` chooses how an endpoint is spoken to: `chat_completions`, the default, or
`generate_content`, the interface of a cloud's regional endpoint (`adapters/driven/models/vertex/`).
Such an endpoint's credential is a service account's key file. The adapter exchanges it for an
access token before a call (RFC 7523) and never sends the key itself. With no
`TAKTUS_MODEL_LOCATION`, the region in the endpoint's host decides where it processes:
`europe-*` is `eu`, every other region and the global endpoint `elsewhere`. A residency rule
`eu` then admits it.

Mistral's API is the `chat_completions` dialect (its published OpenAPI specification). It is
configured, not coded: its endpoint, a model, `TAKTUS_MODEL_LOCATION=eu`. The adapter reads its
finish reason `model_length` as an answer cut at a limit. What each provider publishes about
where it processes and whether it trains on what is sent is in
`adapters/driven/models/README.md`, with the page it is quoted from.

## Alternatives

- **An adapter per local server.** Every one of them speaks the dialect the existing adapter
  speaks. A second adapter would repeat it. Rejected.
- **Ship a model server in the compose file.** It would pull several gigabytes at installation,
  and the choice of a model is the organisation's. Rejected: Taktus uses the hardware that is
  there and does not supply it (UC-8.3 §3).
- **Default the location of any named endpoint to `own` under local first.** A remote endpoint
  named without a location would be counted as the organisation's own. Rejected: an outside
  provider is declared, never assumed.

## Consequences

- `adapters/driven/models/openai_compatible/client.py`: the model asked of the server.
- `composition/settings.py`: `TAKTUS_MODEL_LOCAL_FIRST` and `TAKTUS_MODEL_LOCAL_ENDPOINT`.
- `deploy/docker/compose.yml` sets local first, and reaches the host as `host.docker.internal`.
- `tests/fakes/model_service.py` answers `GET /models` as such a server documents it, and
  `tests/fakes/vertex_service.py` stands in for the regional endpoint and its token endpoint.

## Where this promise ends

- A local model may answer worse or slower than a remote one. That it runs is promised. That
  its quality holds is UC-8.4's evaluation.
- The default address is the host's port of one server. A server elsewhere, or on another
  port, is named in `TAKTUS_MODEL_LOCAL_ENDPOINT`. Nothing is installed or started for it.
- A server that serves several models needs `TAKTUS_MODEL_NAME`. Which of them to ask is the
  operator's choice.
- A worker or a connector that calls a provider of its own is not a model of the instance. Its
  location is its own declaration (UC-11.1). The residency rule keeps model steps on `own`
  models, not a coding agent's own calls.
- The model contract's suite speaks chat completions. It does not run against a
  `generate_content` endpoint. That adapter is held to the port by its own tests against a
  stand-in, and is not *verified* until a suite for its dialect exists.
- Neither provider is called live by this repository (DEC-0225). Their stand-ins reproduce the
  published interfaces as of 2026-11-07.
- A provider's statement about training is the provider's. Taktus quotes it and cannot check it.
- With local first and nothing listening at the address, a step on a model fails with the
  endpoint named. Processes without such a step run as before.
