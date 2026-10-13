# NTC-0208 — The model endpoint in use reports no cached tokens

**Mode entry:** M2.8
**Kind:** spend
**Decided:** 2026-10-13
**Raised in:** the pull request that closes issue #312, after #372

## 1. What was decided

The session spent on the model credential the owner provided (NEED-0024) to verify which usage
shape the endpoint in use reports, as issue #312's last condition asks, instead of assuming it.

1. **What was sent.** Two identical calls to the endpoint the installed instance and the
   workstation use, the provider's chat-completions dialect with the model of DEC-0019: a
   system prompt of about 7 000 tokens, five tokens of output.
2. **What it reported.** Both calls reported `prompt_tokens: 7067`, `completion_tokens: 5`,
   `total_tokens: 7072` — no cached input, in neither shape #312 reads (nested under
   `prompt_tokens_details` or at the top of the usage). The second call, identical, was not
   reported as read from a cache.
3. **What follows.** The endpoint's declared usage kinds stay at the default, `input,output`
   (`TAKTUS_MODEL_USAGE_KINDS`, `model.usageKinds`); M-04 holds it to that. Its rate-limit
   headers are `x-ratelimit-*`; a `429` was not provoked, so whether it carries `Retry-After`
   is not verified here.

## 2. The evidence

The two usage blocks above, read on 2026-10-13 from a script that printed only the usage and
the rate-limit headers. The cost: about 14 000 input and 10 output tokens at the model's
price, under USD 0.02.

## 3. What was considered

- **Provoking a `429`.** It needs a burst past the account's limit of 10 000 requests or 12
  million tokens per minute, far beyond USD 1. Not done.
- **Asking the provider's documentation instead.** It describes the provider's own dialect,
  not what its chat-completions dialect reports through this endpoint. The call is the fact.

## 4. Which entry permits it

M2.8 of `docs/decisions/anchors.taktus.md`: spending on a credential the owner provided, to
derive or verify a fact instead of asking, within the purpose its needs request names, up to
USD 1 per task. The credential is the model key of NEED-0024; the task is #312; the spend was
under USD 0.02.
