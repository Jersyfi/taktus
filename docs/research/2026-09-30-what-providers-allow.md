# What a model provider allows a budget to be — 2026-09-30

**Why this file exists.** A budget promise may only be as strong as the provider permits
(`docs/vision/principles.md`, principle 8: *a budget promise stronger than the provider allows*
is forbidden). The model contract therefore makes every model adapter **declare** what it can
compute before a call (`contracts/model/v1`, `Calculability`), and Taktus derives from the
declaration which budget it can enforce. This file is the evidence the declarations of
2026-09-30 rest on.

**How it was made.** Web research by a session on 2026-09-30. Every source was accessed on
that date; the source keys (`[A1]`) point to the list at the end of each provider section. Some
pages could not be read in full: the OpenAI Help Center (HTTP 403), the Vertex AI pricing table
and the Gemini `countTokens` page (partly). Claims resting on them are marked **nv** (not
verified). Where a claim was load-bearing it was checked against the verbatim text or with a
direct request.

**It expires.** Providers change their terms without notice. This is a record of one date, not
a description of today; the declaration of an adapter is revisited when its provider changes,
and the date above says how old this evidence is. Product names appear here and only here: the
contract and the core name none (ADR-0003).

---

## (a) Summary

Legend: **yes** / **no** / **partly** / **n/a** / **nv** (not verified). A marker such as ¹ points
to the footnotes below the table; the provider sections carry the detail.

| Provider | 1 Exact input count before the call | 2 Hard output cap (thinking inside it, billed) | 3 Prices per kind published / machine-readable | 4 Pre-flight cost estimate | 5 Provider-side spend limit | 6 Billing basis | 7 Cache pricing | Usage broken down in the response |
|---|---|---|---|---|---|---|---|---|
| Anthropic API | partly¹ | yes² | yes / no³ | no | yes, hard (organisation and workspace)⁴ | per token (+ per search, per container-hour) | read 0.1× (0.05× / 0.025× on some models); write 1.25× (5 min) or 2× (1 h) | yes⁵ |
| Anthropic subscription plans (the coding agent) | n/a | n/a | no (the quota is opaque)⁶ | no | yes, a hard quota; extra usage has a monthly cap⁶ | a 5-hour session and a weekly limit; extra usage at API rates | n/a | no (progress bars only)⁶ |
| OpenAI API | yes⁷ | yes⁸ | yes / no⁹ | no | yes, hard (organisation and project), with a slight overshoot¹⁰ | per token (+ per-call tool fees) | automatic; newer models: write 1.25×, read 0.1×¹¹ | yes¹¹ |
| OpenAI subscription plans | n/a | n/a | partly¹² | no | nv¹² | 5-hour and weekly windows; credits per token after that¹² | credits for cached input listed¹² | nv |
| Google Gemini API / Vertex AI | partly¹³ | yes¹⁴ | yes / partly¹⁵ | no | partly: a hard tier cap; project and billing caps are experimental or preview, with latency¹⁶ | per token (+ grounding per request, cache storage per hour) | implicit: a discount, no storage fee; explicit: creation at input price + storage per hour, TTL 60 min by default¹⁷ | yes¹⁸ |
| Mistral | partly¹⁹ | partly²⁰ | yes / no²¹ | no | yes, hard (organisation and workspace, monthly)²² | per token (+ per-call tool fees) | read at 10 % of input; write fee and TTL not documented²³ | partly²³ |
| Scaleway Generative APIs (hosted in the EU) | partly²⁴ | partly²⁵ | yes / **yes**²⁶ | partly (a workload estimator only)²⁷ | no hard cap; billing alerts only²⁸ | per token, minimum unit 1,000 tokens; dedicated deployments per hour²⁹ | automatic, a discounted read; the TTL is a heuristic³⁰ | nv |
| AWS Bedrock | yes (supported models)³¹ | partly³² | yes / **yes**³³ | no (a count only)³¹ | no native hard cap; budgets alert and act, 8–12 h late³⁴ | per token; provisioned throughput per model unit and time³³ | per model: 5 min / 1 h for some, write 1.25× and read 90 % off for others³⁵ | partly³⁶ |
| Azure OpenAI | partly³⁷ | yes³⁸ | yes / partly³⁹ | no | no: budgets alert only, 8–24 h late⁴⁰ | per token; provisioned deployments per unit | read discounted; writes charged on the newest models; retention 5–10 min (max 1 h) or up to 24 h⁴¹ | yes⁴² |
| Local inference (llama.cpp, vLLM, Ollama) | partly⁴³ | yes, if set (unlimited by default)⁴⁴ | n/a (own hardware) | n/a | n/a | hardware time and energy | no money price; it saves time only⁴⁵ | partly⁴⁶ |

**Footnotes.**
1. The endpoint is free, and the provider calls the count "an estimate" that "might differ by a small amount". It refuses server tools, MCP and URL or file sources.
2. `max_tokens` is "a hard cap on total output … thinking and response text combined". Thinking is billed as output, in full.
3. Prices are on a documentation page with multipliers. No pricing API was found.
4. Usage stops at the tier cap or at a lower limit the customer sets, with an error. The latency of enforcement is not documented.
5. The response reports cache creation (split by TTL), cache reads, thinking tokens and server-tool calls.
6. Limits reset every five hours, and there is a weekly limit. No unit is published. Extra usage is billed at API rates, with a monthly cap the customer sets.
7. `POST /responses/input_tokens` returns "the exact count the model will receive".
8. `max_output_tokens` limits reasoning and visible tokens together. Reasoning is billed as output. A truncated response still costs money.
9. The pricing page covers input, cached input, cache write, output, batch modes and tool calls. No machine-readable price feed was found.
10. Hard limits answer with an error. "Enforcement is not instantaneous."
11. Newer models report cached tokens, cache-write tokens and reasoning tokens.
12. A 5-hour window and weekly limits; one plan tier has no 5-hour limit. Credits are priced per million input, cached-input and output tokens. The help page was unreadable (403).
13. `countTokens` exists. For multimodal input the count is "an estimation". Exactness for text is not stated.
14. `max_output_tokens` includes thought tokens, which are billed as output at full length.
15. A cloud billing pricing API is machine-readable. It is not verified that it covers the developer API's SKUs.
16. See the provider section.
17. See the provider section.
18. The response reports cached, thought and tool-use prompt token counts.
19. An open-source tokenizer library exists. Parity with billing is not stated.
20. `max_tokens` exists. Whether reasoning tokens count towards it is not documented.
21. A web page, with per-call tool fees. No price feed was found.
22. API access is suspended at the limit. The latency is not documented.
23. The response reports cached prompt tokens. Reporting of reasoning tokens is not verified.
24. No count endpoint is documented; the FAQ points to each model's tokenizer files.
25. Per-model output limits exist and cannot be raised. Whether reasoning is inside them is not verified.
26. A public product catalogue API returns input, output, cached-input and batch prices per model as JSON.
27. The estimator models a monthly workload, not a single call.
28. "You cannot configure a specific threshold after which your usage will be blocked."
29. See the provider section.
30. See the provider section.
31. `CountTokens` is free and "will match the token count that would be charged". Some models need a second endpoint.
32. The cap is a model parameter passed through to the model; its semantics there were not separately verified.
33. A bulk price-list API (JSON and CSV) includes cache read, cache write for both TTLs, and batch SKUs.
34. See the provider section.
35. See the provider section.
36. The usage report has cache read, cache write and a TTL split, but no reasoning-token field.
37. No documented count endpoint. The local tokenizer library is limited for images, files and tools.
38. The output limits "cover reasoning tokens, visible output tokens, and formatting tokens".
39. A retail prices API lists the service's meters, including cached input for older models. Meters for the newest models and for cache writes were not found.
40. "Resources aren't affected, and your consumption isn't stopped."
41. See the provider section.
42. The response reports cached tokens, cache-write tokens on the newest models, and reasoning tokens.
43. llama.cpp and vLLM have `/tokenize`; vLLM can render the exact prompt token identifiers. Ollama documents no tokenize endpoint.
44. `n_predict` / `num_predict` default to −1, which means unlimited generation.
45. A reused key-value cache costs no money; it saves time.
46. llama.cpp reports evaluated, predicted and cached tokens. Ollama reports counts and durations, with no thinking split (nv).

---

## (b) Per provider

### Anthropic — the API

1. **Input count.** `POST /v1/messages/count_tokens` takes the same input as a message, tools, images and PDFs included [A1]. The documentation says: "The token count is an estimate. In some cases, the actual number of input tokens used … might differ by a small amount." [A1] It is free and rate-limited separately [A1]. It refuses server tools, the MCP connector and URL or file sources [A1]. It "provides an estimate without using caching logic", so it cannot say whether input will be read from the cache or written to it [A1]. Newer models use a tokenizer that produces about 30 % more tokens, so a count is taken per target model [A1][A2]. **Partly**: close, not guaranteed exact.
2. **Output cap.** "`max_tokens` is a hard cap on total output for the request, thinking and response text combined. Claude never generates past it." [A4] In a tool loop each request has its own cap, so the cap does not bound a whole turn [A4]. Thinking is billed as output in full, whatever is displayed [A4]. The older `budget_tokens` "is a target rather than a strict cap" [A5].
3. **Prices.** A documentation page lists, per model: base input, 5-minute cache write, 1-hour cache write, cache hit, output; batch at a 50 % discount; web search per 1,000 searches; code execution per container-hour beyond an allowance; a multiplier for a regional option; and per-session fees for a managed agent product [A2]. No pricing API was found. **Published: yes. Machine-readable: no.**
4. **Pre-flight estimate.** None beyond the count, which the documentation presents as a way to "manage rate limits and costs" [A1]. **No.**
5. **Spend limits.** Each tier has a monthly cap; at the cap "API usage pauses until 00:00 UTC on the first day of the next month" and requests fail [A6]. A lower customer limit fails requests too [A6]. Workspaces can carry their own limits [A6]. Latency and overshoot are not documented. **Hard.**
6. **Basis.** Per token, plus per-search and per-container-hour fees [A2].
7. **Cache.** Writes cost 1.25× base input (5-minute TTL) or 2× (1 hour) [A2][A3]. Reads cost 0.1× base input, less on some newer models [A2]. Caching is automatic or uses explicit breakpoints [A2].

**Usage breakdown: yes** [A2][A3][A4]. The response reports the uncached input after the last breakpoint, cache creation and cache reads (with the TTL split), output with thinking tokens, and server-tool calls. Total input = cache read + cache creation + uncached input [A3].

Sources: [A1] https://platform.claude.com/docs/en/build-with-claude/token-counting · [A2] https://platform.claude.com/docs/en/about-claude/pricing · [A3] https://platform.claude.com/docs/en/build-with-claude/prompt-caching · [A4] https://platform.claude.com/docs/en/build-with-claude/thinking-steering-and-cost · [A5] https://platform.claude.com/docs/en/build-with-claude/extended-thinking · [A6] https://platform.claude.com/docs/en/api/rate-limits

### Anthropic — subscription plans (the coding agent's subscription mode)

- **Basis.** Plan usage limits "are shared across Claude and Claude Code" [C3]. "Your session-based usage limit will reset every five hours. Max plans also have a weekly usage limit that applies across all models." [C1] The weekly limit resets at a time assigned to the account [C1].
- **Unit.** Not published. Usage depends on conversation length, features, model and effort [C4]. The provider "may limit your usage in other ways … at our discretion" [C1].
- **Over the limit.** Usage credits can be enabled, "billed at standard API rates", with "a maximum amount you're willing to spend on usage credits each month" [C2].
- **Questions 1–4 and 7:** n/a. There is no per-call accounting against the quota.
- **Usage breakdown.** No per-call figure; the settings page shows progress bars for the session and the week (seen in search snippets; the article was not read in full).

Sources: [C1] https://support.claude.com/en/articles/11049741-what-is-the-max-plan · [C2] https://support.claude.com/en/articles/12429409-extra-usage-for-paid-claude-plans · [C3] https://support.claude.com/en/articles/11145838-using-claude-code-with-your-pro-or-max-plan · [C4] https://support.claude.com/en/articles/11647753-how-do-usage-and-length-limits-work

### OpenAI — the API

1. **Input count.** `POST /responses/input_tokens` takes "text, messages, images, files, tools, or conversations" and returns "the exact count the model will receive" [O1]. A local tokenizer "work[s] for plain text" and is limited for images, files, tools and schemas [O1]. Whether the endpoint is charged is not stated (nv). **Yes, exact.**
2. **Output cap.** `max_output_tokens` limits "the total number of tokens the model generates, including reasoning tokens, visible output tokens, and non-visible formatting tokens" [O2]. Reasoning tokens "are billed as output tokens" [O2]. A response cut at the cap can "incur costs for input and reasoning tokens without receiving a visible response" [O2].
3. **Prices.** The pricing page lists input, cached input, cache write, output, processing modes and tool calls; web search is per 1,000 calls plus its content tokens [O4]. No machine-readable feed was found [O4].
4. **Pre-flight estimate.** None; only the count. **No.**
5. **Spend limits.** Hard limits at organisation and project level answer with an error [O5]. Alerts notify and let traffic continue [O5]. "Enforcement is not instantaneous, so recorded spend can slightly exceed the configured amount." [O5] Limits reset monthly; per-key limits are not documented [O5]. **Hard, with a small overshoot.**
6. **Basis.** Per token, plus per-call tool fees [O4].
7. **Cache.** On by default for supported models [O3]. On the newest family, writes cost 1.25× uncached input and reads 0.1× (0.05× on one model), with one TTL option [O3]. Older models charge nothing for a write; retention is in memory (about 5–10 minutes, up to an hour) or 24 hours [O3].

**Usage breakdown: yes** — cached tokens, cache-write tokens [O3] and reasoning tokens [O2].

Sources: [O1] https://developers.openai.com/api/docs/guides/token-counting · [O2] https://developers.openai.com/api/docs/guides/reasoning · [O3] https://developers.openai.com/api/docs/guides/prompt-caching · [O4] https://developers.openai.com/api/docs/pricing · [O5] https://developers.openai.com/api/docs/guides/spend-limits

### OpenAI — subscription plans

- **Windows.** Local and cloud work share the plan's allowance, and "Weekly limits may also apply" [O6]. "Pro plans currently have no five-hour limit." [O6] That a 5-hour window applies to other tiers comes from a search snippet; the help article returned 403 (**nv**).
- **Beyond the allowance.** Credits at listed rates per million input, cached-input and output tokens [O6]. An API key can be used instead, at API rates [O6].
- **A cap on credits.** Not documented on the page read (**nv**).

Sources: [O6] https://learn.chatgpt.com/docs/pricing (redirected from https://developers.openai.com/codex/pricing) · https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan (403, not read)

### Google — Gemini API and Vertex AI

1. **Input count.** `models.countTokens` "Runs a model's tokenizer on input `Content` and returns the token count" [G1]; exactness is not stated. On Vertex it is free with a quota of 3,000 requests per minute [G7], and "token counts for multimodal inputs … are an estimation" [G7]. **Partly.**
2. **Output cap.** `max_output_tokens` "sets the maximum number of tokens a response can generate, including thought tokens" [G3]. "Pricing is based on the full thought tokens" [G3]. `thinking_level` guides, it does not cap [G3].
3. **Prices.** Output "including thinking tokens"; cache storage per token-hour; a 50 % batch discount; higher prices above 200k-token prompts on some models; grounding per request after a free quota [G4]. The cloud billing pricing API is machine-readable [G12]; that it covers the developer API's SKUs is **nv**. **Published: yes. Machine-readable: partly.**
4. **Pre-flight estimate.** None. **No.**
5. **Spend limits.** A monthly tier cap pauses "service … for all projects linked to that billing account until the start of the next billing cycle" [G6]. Project caps in the studio are "experimental … subject to overages for around a 10 minute latency period" [G6]. Billing spend-cap budgets (preview) pause usage "until you manually lift the spend cap", and enforcement "isn't instant and any cost overages are billed as normal" [G11]. Alert-only budgets do not cap [G10]. **Partly hard, with latency.**
6. **Basis.** Per token, plus grounding fees and cache storage per hour [G4].
7. **Cache.** Implicit caching is on by default for newer models with "no cost saving guarantee" [G5][G5b]; on Vertex a 90 % discount on cached tokens, no storage cost [G8]. Explicit caching bills creation "at the standard input token price" plus storage per hour, default TTL 60 minutes [G8][G5b].

**Usage breakdown: yes** — prompt, cached content, candidates, thoughts and tool-use prompt token counts [G2][G9].

Sources: [G1] https://ai.google.dev/api/tokens · [G2] https://ai.google.dev/gemini-api/docs/generate-content/tokens · [G3] https://ai.google.dev/gemini-api/docs/thinking · [G4] https://ai.google.dev/gemini-api/docs/pricing · [G5] https://ai.google.dev/gemini-api/docs/caching · [G5b] https://ai.google.dev/gemini-api/docs/generate-content/caching · [G6] https://ai.google.dev/gemini-api/docs/billing · [G7] https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/get-token-count · [G8] https://docs.cloud.google.com/vertex-ai/generative-ai/docs/context-cache/context-cache-overview · [G9] https://cloud.google.com/vertex-ai/generative-ai/pricing (partly read) · [G10] https://docs.cloud.google.com/billing/docs/how-to/budgets · [G11] https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps · [G12] https://docs.cloud.google.com/billing/docs/how-to/get-pricing-information-api

### Mistral

1. **Input count.** An open-source library provides "the tokenizers, validation and normalization code" [M6]; parity with billing is not stated, and a count endpoint is not verified. **Partly.**
2. **Output cap.** `max_tokens` is "the maximum number of tokens to generate in the completion" [M4]. Whether reasoning tokens count towards it, and how they are billed, is not documented [M4][M5]. **Partly.**
3. **Prices.** Input, cached input and output per token are published; batch "at half price" [M3][M3b]. Tool fees per 1,000 calls [M3b]. A web page only. **Published: yes. Machine-readable: no.**
4. **Pre-flight estimate.** None. **No.**
5. **Spend limits.** Monthly organisation and workspace limits; at the limit "API access can be suspended until the next month begins or an admin increases the limit" [M1]. Latency and alerts are not documented. **Hard.**
6. **Basis.** Per token, plus per-call tool fees and document processing per page [M3b].
7. **Cache.** Opt-in; "cached prompt tokens are billed at 10% of the standard input token price" [M2]. A write fee and a TTL are not documented [M2].

**Usage breakdown: partly** — cached prompt tokens; billable uncached input = prompt tokens − cached tokens [M2]. A reasoning-token field is **nv**.

Sources: [M1] https://docs.mistral.ai/admin/billing-usage/usage-limits · [M2] https://docs.mistral.ai/studio-api/conversations/advanced/prompt-caching · [M3] https://docs.mistral.ai/inference/pricing · [M3b] https://mistral.ai/pricing/api · [M4] https://docs.mistral.ai/api/endpoint/chat · [M5] https://docs.mistral.ai/studio/conversations/reasoning · [M6] https://github.com/mistralai/mistral-common

### Scaleway Generative APIs (hosted in the EU)

Chosen because its documentation and its price API could be sourced. OVHcloud AI Endpoints is also billed per token with a batch discount (from search snippets only) and was not researched further (**nv**).

1. **Input count.** No count endpoint; "the exact token count and definition depend on the tokenizer used by each model", and the FAQ points to each model's tokenizer configuration [S1]. **Partly.**
2. **Output cap.** Per-model maximum outputs "you cannot increase", with "uncontrolled billing" given as one reason [S1]. Reasoning accounting is **nv**. **Partly.**
3. **Prices.** A public product catalogue API returns per-model SKUs as JSON: input, output and cached input, each in real-time or batch mode, in EUR per 1,000 tokens [S3]; queried directly on 2026-09-30. **Machine-readable: yes.**
4. **Pre-flight estimate.** A console estimator models monthly cost from users, queries and hours, "based on standard benchmarks" [S2]; nothing per call. **Partly.**
5. **Spend limits.** "You cannot configure a specific threshold after which your usage will be blocked"; alerts warn [S1]. "Your total billing remains limited by the amount of tokens you can consume within rate limits." [S1] Metrics lag by up to 5 minutes [S1]. **No hard cap.**
6. **Basis.** Per token; "the minimum billing unit is 1,000 tokens"; the free tier "is applied to the most expensive tokens first" [S1]. Dedicated deployments are billed per hour, used or not [S1].
7. **Cache.** Automatic; eviction depends on request frequency; cached input "at a discounted rate" [S1]; only some models list a cached-input SKU [S3].

**Usage breakdown:** **nv** for the response body; the metrics expose input and output tokens [S1].

Sources: [S1] https://www.scaleway.com/en/docs/generative-apis/faq/ · [S2] https://www.scaleway.com/en/docs/generative-apis/reference-content/cost-estimator/ · [S3] https://api.scaleway.com/product-catalog/v2alpha1/public-catalog/products?product_types=generative_apis

### AWS Bedrock

1. **Input count.** `CountTokens` is free, and "the token count returned by this operation will match the token count that would be charged" [B1]. Support varies per model; some need a second endpoint [B1]. **Yes, for supported models.**
2. **Output cap.** A model-specific parameter passed through to the model; its semantics there were not separately verified. **Partly.**
3. **Prices.** On-demand per token, batch on selected models, provisioned throughput by model unit and time, feature fees [B4]. The price-list bulk and query APIs provide JSON and CSV [B5], and the offer file carries separate SKUs for input, output, cache read, cache write (both TTLs), batch and throughput [B5b]. The list is "for informational purposes only"; the pricing page prevails [B5]. **Machine-readable: yes.**
4. **Pre-flight estimate.** The count is offered to "estimate costs before sending inference requests"; the arithmetic is the caller's [B1]. **No.**
5. **Spend limits.** Budgets alert, and budget actions can apply a policy or target instances [B7]. "AWS Budgets information is updated up to three times a day. Updates typically occur 8–12 hours after the previous update." [B6] One "might incur additional costs … before AWS Budgets can notify you" [B6]. No native hard cap was found. **Soft, delayed.**
6. **Basis.** Per token, or per model unit and time for provisioned throughput [B4].
7. **Cache.** Reads "at the model's cache-read rate"; writes, "depending on the model", above the input rate [B2]. TTLs and multipliers vary per model family [B2]. No caching with batch [B2].

**Usage breakdown: partly** — non-cached input, output, cache read, cache write and a TTL split, but no reasoning-token field [B2][B3].

Sources: [B1] https://docs.aws.amazon.com/bedrock/latest/userguide/count-tokens.html · [B2] https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html · [B3] https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_TokenUsage.html · [B4] https://aws.amazon.com/bedrock/pricing/ · [B5] https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/price-changes.html · [B5b] https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonBedrockFoundationModels/current/eu-central-1/index.json · [B6] https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html · [B7] https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-controls.html

### Azure OpenAI

1. **Input count.** No pre-call count endpoint was found in the provider's documentation; a Q&A answer seen only as a snippet says none exists (**nv**). A local tokenizer is limited for images, files and tools [O1]. **Partly.**
2. **Output cap.** "Both limits cover reasoning tokens, visible output tokens, and formatting tokens." [Z2] Reasoning is billed as output [Z2]. **Yes.**
3. **Prices.** A retail prices API is "an unauthenticated experience to get retail rates for all Azure services" [Z3]; a direct query returned the service's meters, with cached input for older models [Z3b]. No meters for the newest models or for cache writes turned up. **Partly.**
4. **Pre-flight estimate.** None. **No.**
5. **Spend limits.** "Resources aren't affected, and your consumption isn't stopped." [Z4] "Cost and usage data is typically available within 8-24 hours and budgets are evaluated against these costs every 24 hours." [Z4] Action groups can trigger automation [Z4]. **Soft only.**
6. **Basis.** Per token for standard deployments; provisioned deployments per unit [Z3b].
7. **Cache.** Reads discounted; "up to 100% discount" on provisioned deployments [Z1]. Older models "don't charge extra to write to the cache"; on the newest, "cache writes can incur charges" [Z1]. In-memory retention clears within 5–10 minutes and always within an hour; extended retention up to 24 hours at the same price [Z1].

**Usage breakdown: yes** — cached tokens, cache-write tokens on the newest standard deployments, and reasoning tokens [Z1][Z2].

Sources: [Z1] https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/prompt-caching · [Z2] https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/reasoning · [Z3] https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices · [Z3b] https://prices.azure.com/api/retail/prices?$filter=productName eq 'Azure OpenAI' and armRegionName eq 'swedencentral' · [Z4] https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets

### Local inference (llama.cpp, vLLM, Ollama)

1. **Input count.** llama.cpp has `POST /tokenize` [L1]; vLLM has `/tokenize` and `/detokenize` [L2b] and can render the exact prompt token identifiers of a request without running it [L2]; Ollama documents no tokenize endpoint [L3]. Whether llama.cpp's endpoint applies the chat template is **nv**. **Partly.**
2. **Output cap.** llama.cpp `n_predict` is "the maximum number of tokens to predict", −1 meaning unlimited [L1]; Ollama `num_predict` defaults to "-1, infinite generation" [L3b]. **Yes, but only when set.** vLLM's `max_tokens` is **nv** (the page was rate-limited).
3.–5. **Prices, estimate, spend limits:** n/a. The cost is one's own hardware time and energy, and nobody else limits it.
6. **Basis.** Hardware hours and energy: the cost follows wall-clock time, not tokens.
7. **Cache.** llama.cpp reuses the key-value cache "from a previous request if possible" [L1]; that saves time, not money.

**Usage breakdown: partly** — llama.cpp reports evaluated, predicted and cached tokens and timings [L1]; Ollama reports counts and nanosecond durations [L3]. The durations are what make a hardware cost recomputable.

Sources: [L1] https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md · [L2] https://raw.githubusercontent.com/vllm-project/vllm/main/docs/serving/online_serving/openai_compatible_server.md · [L2b] https://raw.githubusercontent.com/vllm-project/vllm/main/docs/usage/security.md · [L3] https://github.com/ollama/ollama/blob/main/docs/api.md · [L3b] https://raw.githubusercontent.com/ollama/ollama/main/docs/modelfile.mdx

---

## (c) What this means for a budget

Five findings hold across the providers.

- **No provider enforces a budget per call.** Every provider-side limit is monthly and per account, organisation, project or workspace. The documented ones act late: "not instantaneous", about ten minutes, or hours. A budget per step or per run is therefore held by the caller, which is Taktus.
- **The caller can bound a call's cost before it.** Three things are needed: the input can be counted, the output is hard-capped with reasoning inside the cap, and the price of every consumption kind is known. The bound is the input count at the most expensive input rate that can apply, plus the output cap at the output rate, plus a cap on per-call tool fees.
- **The exact cost is known only afterwards.** It is recomputed from the usage breakdown of the response. Where the breakdown lacks a kind — reasoning, cache write, tool calls — the recomputation becomes an estimate.
- **Whether input will be read from the cache is not knowable before the call** ([A1] says so). The bound before the call therefore assumes the most expensive case, a cache write.
- **Tokenizers differ per model.** A count taken for one model does not carry over to another [A1].

Which budget can be enforced, per provider:

| Provider | The budget that can be enforced |
|---|---|
| OpenAI API | **A currency budget converted into tokens and held per call.** The count is exact [O1], the cap is hard and includes reasoning [O2], the usage splits cached, cache-write and reasoning tokens [O3][O2]. The prices come from a web page, so the price table is maintained by hand [O4]. Web-search fees lie outside the token cap. |
| Anthropic API | **A currency budget held per call as an upper bound, with a small margin on input.** The count is an estimate that may differ slightly and cannot count server tools [A1]. The cap is hard and includes thinking [A4]. The usage is complete enough to recompute exactly [A2][A3][A4]. The prices come from a web page [A2]. |
| AWS Bedrock | **A currency budget held per call** for models whose count is supported and exact [B1]. The prices are machine-readable [B5b]. Reasoning is not separable in the usage report [B3], so it is recomputed only in total. |
| Google Gemini API / Vertex AI | **A currency budget held per call for text; only an estimate for multimodal input** [G7]. The cap is hard and includes thinking [G3]. Explicit cache storage is billed per hour, outside any call [G8], and is a time-based cost of its own. |
| Azure OpenAI | **A currency budget only as an estimate** where the input carries tools, images or files, since no count endpoint is documented. For plain text a local tokenizer gives a practical bound. The cap is hard [Z2] and the usage breakdown complete [Z1]. |
| Mistral | **A currency budget only as an estimate.** The tokenizer's parity with billing is not documented [M6], and whether reasoning is inside `max_tokens` is not documented either [M4][M5]. |
| Scaleway | **A currency budget only as an estimate.** No count endpoint, reasoning accounting not verified [S1]. The prices are machine-readable [S3]. Billing rounds to a minimum unit of 1,000 tokens [S1]. |
| Subscription plans (both vendors) | **Only a share of a time window.** The unit of the quota is not published [C1][C4]. A budget can only say "this share of the 5-hour and the weekly allowance". A currency budget cannot be enforced at all. |
| Local inference | **No currency budget per token; a hardware-time budget instead.** Output is bounded only when a cap is set, because the default is unlimited [L1][L3b]. The cost is an estimate from the recorded durations times the hardware's rate. |

**The dialect the model adapter speaks today** — the chat-completions dialect over any endpoint —
has no count endpoint of its own. What it can promise is an **upper bound**, not an exact count:
a tokenizer that works on bytes never produces more tokens than the text has bytes, plus a fixed
overhead per message. That bound over-reserves, and it is safe. Its declaration says exactly
that (`contracts/model/v1`, `input_count: upper_bound`).
