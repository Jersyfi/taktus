An `llm` step names a **purpose**, such as `writing`, never a model. The instance's
configuration binds each purpose to a model. Adding a model provider is therefore configuration
first, and code only where the provider speaks a dialect Taktus does not.

## A provider that speaks a known dialect

Two dialects are spoken, chosen by `TAKTUS_MODEL_DIALECT`:

- `chat_completions`, the default: `POST {endpoint}/chat/completions`. Most providers' APIs, model
  servers on the organisation's own hardware and pass-through gateways answer it.
- `generate_content`: `POST {endpoint}/{model}:generateContent`, the dialect of one cloud's
  regional endpoints.

One model is configured with `TAKTUS_MODEL_ENDPOINT`, `TAKTUS_MODEL_NAME` and
`TAKTUS_MODEL_PURPOSES`, and declares where it processes with `TAKTUS_MODEL_LOCATION`: `own`,
`eu` or `elsewhere`. Several models, tried in order, are `TAKTUS_MODELS`. Its key is the file
`TAKTUS_CREDENTIAL_MODEL_API_KEY_FILE` names. `.env.example` describes every one of these.
`src/taktus/adapters/driven/models/README.md` gives worked settings per provider.

## A provider with a dialect of its own

Its adapter implements the model port, `src/taktus/ports/model.py`, in a directory of its own
under `src/taktus/adapters/driven/models/`. Only that directory names the provider. The adapter
is proven against a fake of the provider's published interface, in `tests/adapters/models/`.

Either way, the adapter declares what it can promise before a call, and the conformance suite
checks that the endpoint keeps it. The rest of this page is the contract's own text.
