# NTC-0206 — Every cached token is booked by its kind, and a provider's delay is kept

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-13
**Raised in:** the pull request for issue #312

## 1. What was decided

ADR-0005 (sixth amendment) and ADR-0043 (amendment of 2026-10-13) are the decision; this notice
records the change of behaviour.

1. **Cached input is booked wherever the endpoint reports it.** The model adapter books
   `cache_creation_input_tokens` as `cache_write` and `cache_read_input_tokens` as `cache_read`,
   beside the nested `prompt_tokens_details.cache_write_tokens` and `cached_tokens`. Before, the
   top-level fields were ignored and their tokens booked as uncached input. Where both shapes
   report a kind, the larger count is booked once. Cached tokens that exceed `prompt_tokens`
   make the input tokens their sum.
2. **The operator declares the price kinds the endpoint reports.** `TAKTUS_MODEL_USAGE_KINDS`
   (chart value `model.usageKinds`), unset `input,output`, becomes the adapter's `usage_kinds`.
   Before, the adapter always declared `input,output`. Conformance check M-04 holds the endpoint
   to the declaration, and the suite reads both shapes.
3. **A `429`'s `Retry-After` defers the job by that delay.** The delay is on the step's open
   block and in the block's record. It is never shorter than the runner's first delay. A delay
   that reaches past the step's ceiling ends the wait at once, and the run escalates. Before,
   the header was dropped and the runner's doubling delay applied.

## 2. The evidence

- `docs/research/2026-10-12-devops-review.md` §G1: 8 000 writes reported at the top level were
  booked as 10 000 input and no cache write.
- `tests/adapters/models/test_openai_compatible.py`
  `test_every_cached_token_is_booked_by_its_kind_in_either_shape` (that case, and every other
  shape), `test_a_completion_books_cache_writes_in_either_shape`,
  `test_a_rate_limit_passes_on_the_delay_its_retry_after_names`.
- `tests/conformance/test_model_v1.py` `test_the_adapter_splits_usage_by_the_dialect_rule` and
  `test_m04_holds_a_declared_cache_write_to_either_shape`.
- `tests/components/run/test_blocked_time.py`
  `test_a_provider_s_retry_after_is_recorded_with_the_block` and
  `test_a_retry_after_past_the_ceiling_ends_the_wait_at_once`;
  `tests/components/run/test_runner.py`
  `test_a_provider_s_retry_after_defers_the_job_by_that_delay`.
- Not yet: which shape each provider in use returns. Issue #312 keeps that verification, under
  the spend cap of M2.8.

## 3. What was considered

- **A setting for whether `prompt_tokens` includes the cached tokens.** It would let an
  operator state the one case the rule cannot tell. Not taken before the providers in use are
  verified; the live verification of #312 decides whether it is needed.
- **Cap the provider's delay at the runner's longest delay, sixty seconds.** The provider would
  be asked again before it said it would answer, and every such try is a wasted call. Not taken.
- **Keep waiting when the provider's delay passes the ceiling.** The run would wait longer than
  the ceiling promises and escalate later for the same reason. Not taken.

## 4. Which entry permits it

M2.4 of `docs/decisions/anchors.taktus.md`: "A change of what the software does, made inside an
agreed scope, that breaks no contract, moves no limit or autonomy level and says nothing
public." The scope is issue #312, accepted with the DevOps review (DEC-0187). The model
contract gains a description of the dialect's split and an example; no schema changes, and
nothing that conformed stops conforming. No limit or level moves: the ceiling stays one hour.
Nothing public is said. The ADR amendments are M1.9.
