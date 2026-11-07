# Models

Every model is reached through the model port (`src/taktus/ports/model.py`) and holds to
`contracts/model/v1`. A process names a purpose. The configuration decides which model serves
it (ADR-0116), and where that model processes (`TAKTUS_MODEL_LOCATION`, UC-11.1). Product names
appear here and in the adapters' own modules, never in the core.

Two dialects are spoken, chosen by `TAKTUS_MODEL_DIALECT`:

| Dialect | Adapter | Spoken by |
|---|---|---|
| `chat_completions` (default) | `openai_compatible/` | a vendor's API that serves `POST {endpoint}/chat/completions`, a model server on the organisation's own hardware, a pass-through gateway |
| `generate_content` | `vertex/` | Vertex AI's `POST {endpoint}/{model}:generateContent` on a regional endpoint |

## Providers proven against stand-ins

The project itself uses Anthropic only (DEC-0225). Every other provider is proven against a
stand-in built from its published interface (DEC-0226), in `tests/adapters/models/`. None of
them is called live by this repository.

### A model server on the organisation's own hardware

Ollama, vLLM's OpenAI-compatible server and llama.cpp's server answer `POST /v1/chat/completions`
and `GET /v1/models`. The most widely used of them listens on port 11434
([docs.ollama.com, *OpenAI compatibility*](https://docs.ollama.com/api/openai-compatibility)).
Declare `TAKTUS_MODEL_LOCATION=own` and `TAKTUS_MODEL_BILLING=per_hardware_time`. A server that
serves one model needs no `TAKTUS_MODEL_NAME`: the adapter asks `GET {endpoint}/models` for it
(ADR-0248). On one machine `TAKTUS_MODEL_LOCAL_FIRST=true` binds every purpose to such a server.

### Mistral (La Plateforme)

Mistral's API serves `POST https://api.mistral.ai/v1/chat/completions` with a bearer key, the
fields `model`, `messages` and `max_tokens`, and answers `choices[].message`,
`choices[].finish_reason` (`stop`, `length`, `model_length`, `error`, `tool_calls`) and `usage`
with `prompt_tokens`, `completion_tokens` and `total_tokens`
([docs.mistral.ai, OpenAPI specification](https://docs.mistral.ai/openapi.yaml)). It is the
`chat_completions` dialect. The adapter reads `model_length` as an answer cut at a limit.

```
TAKTUS_MODEL_ENDPOINT=https://api.mistral.ai/v1
TAKTUS_MODEL_NAME=<a model id the API lists at GET /v1/models>
TAKTUS_MODEL_LOCATION=eu
TAKTUS_CREDENTIAL_MODEL_API_KEY_FILE=<a file holding the API key>
```

- **Where it processes.** Mistral states: "By default, your data is hosted in the European
  Union." A US endpoint it offers hosts data in the United States; declare that one
  `elsewhere` ([help.mistral.ai, *Where do you store my data*](https://help.mistral.ai/en/articles/347629-where-do-you-store-my-data-or-my-organization-s-data)).
- **Training on what is sent.** Mistral's page on training distinguishes its free mode from
  pay-as-you-go. For pay-as-you-go it says customers "have the right to opt out at any time",
  and it does not say that nothing is used by default
  ([help.mistral.ai, *Do you use my user data to train*](https://help.mistral.ai/en/articles/347617-do-you-use-my-user-data-to-train-your-artificial-intelligence-models)).
  An organisation that must exclude training opts out in its Mistral account before it
  configures the model. Taktus cannot see whether it did.

### Vertex AI (Gemini)

Vertex AI serves `POST /v1/{model}:generateContent`, where `{model}` is
`projects/{project}/locations/{region}/publishers/google/models/{model}`, on regional hosts
`https://{region}-aiplatform.googleapis.com` and on a global one. The request carries
`contents` (`role`, `parts[].text`), `systemInstruction` and `generationConfig.maxOutputTokens`.
The answer carries `candidates[].content.parts[].text`, `candidates[].finishReason` (`STOP`,
`MAX_TOKENS` and others), `usageMetadata` (`promptTokenCount`, `candidatesTokenCount`,
`thoughtsTokenCount`, `cachedContentTokenCount`, `totalTokenCount`) and `modelVersion`. Access is
an OAuth 2.0 access token with the scope `https://www.googleapis.com/auth/cloud-platform`
(the service's discovery document, `https://aiplatform.googleapis.com/$discovery/rest?version=v1`).

```
TAKTUS_MODEL_DIALECT=generate_content
TAKTUS_MODEL_ENDPOINT=https://europe-west3-aiplatform.googleapis.com/v1/projects/<project>/locations/europe-west3/publishers/google/models
TAKTUS_MODEL_NAME=<a Gemini model id>
TAKTUS_CREDENTIAL_MODEL_API_KEY_FILE=<a service account's key file, as the console issues it>
```

- **The credential** is the service account's JSON key. The adapter signs an assertion with it
  and exchanges it at the key's `token_uri` for an access token (RFC 7523), kept until a minute
  before it expires. The service account needs the role that may call Vertex AI's prediction
  in that project, and nothing beyond it.
- **Where it processes.** With no `TAKTUS_MODEL_LOCATION`, the region of the endpoint's host
  decides: `europe-*` is `eu`, any other region and the global endpoint are `elsewhere`. Google
  states that on a regional endpoint cached data stays in the selected location, and that the
  global endpoint may serve a request from any region
  ([*Generative AI and data governance*](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/data-governance)).
- **Training on what is sent.** Google states: "Google won't use your data to train or
  fine-tune any AI/ML models without your prior permission or instruction" (same page).
- **Caching.** The same page says published Gemini models cache customer data by default, and
  that durable caching can be switched off per project. That is the project owner's setting.
