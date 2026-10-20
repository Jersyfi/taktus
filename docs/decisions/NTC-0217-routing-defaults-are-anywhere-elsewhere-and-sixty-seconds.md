# NTC-0217 — Routing defaults: anywhere, elsewhere, sixty seconds

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-20
**Raised in:** issue [#328](https://github.com/Jersyfi/taktus/issues/328), in the pull request that closes it
**How it follows:** Principle 11 forbids "sending data outside a configured residency". A tenant that configured none has set no boundary, so its default permits every location, and nothing that works today stops working. The same principle makes an undeclared location the stricter case: a model nobody declared is treated as outside every rule narrower than *anywhere*, so a rule a tenant does set is never met by a guess. UC-11.1 §3 leaves the location to whoever configures the adapter and says Taktus does not verify it. Where two cool-downs were both consistent with ADR-0043, the shorter one was taken: it is the runner's ceiling of one minute for a deferral, and a provider that names its delay overrides it.

## 1. What was decided

ADR-0116 needs three values a tenant or an operator holds before setting one.

1. **A tenant that set no residency rule permits `anywhere`.** `taktusctl residency set`
   narrows it.
2. **A model whose operator declared no location is located `elsewhere`.** A tenant rule of
   `eu` or `own` passes it over. `TAKTUS_MODEL_LOCATION` and `TAKTUS_MODELS_<MEMBER>_LOCATION`
   declare it.
3. **A model cools down for 60 seconds** after a failure, or after a `429` whose answer named no
   delay. `TAKTUS_MODEL_COOL_DOWN_SECONDS` sets it.

All three are product defaults, not the project's.

## 2. The evidence

- Before this change every step on a model was sent to the one configured model, whatever its
  location. The default `anywhere` keeps that, and every test that ran before runs unchanged
  (`tests/components/run/test_blocked_time.py`, `tests/integration/test_triage.py`).
- `tests/components/run/test_model_routing.py`
  `test_a_member_outside_the_tenant_s_residency_rule_is_never_chosen` shows a rule of `eu`
  passing over a model located `elsewhere`.
- `tests/components/governance/test_residency.py`
  `test_a_tenant_that_set_no_rule_permits_anywhere` holds the first default.
- ADR-0037 §3 defers a job by at most a minute when nothing names a delay; the cool-down uses
  the same bound.

## 3. What was considered

- **A default rule of `eu`.** It would follow principle 11 more closely. Every instance whose
  model declares no location would stop routing its steps on upgrade. A tenant's boundary is the
  tenant's to set (UC-11.1 §1). Rejected.
- **An undeclared location treated as `eu`.** A guess about where a provider processes would
  then decide whether a rule holds. Rejected.
- **No cool-down after a failure.** The next step would ask a model that just failed, and fail
  the same way before it moves. Rejected.
- **A cool-down of five minutes.** A model that recovers within a minute would be passed over
  four minutes longer. Rejected: the provider's own `Retry-After` covers a longer limit.

## 4. Which entry permits it

No entry of modes 3 or 4 names a default of a tenant's residency rule, a model's location or a
cool-down. M3.10 names limits on spending, and none of the three limits spending. No entry of
mode 2 names them either, so M2.6 applies.

## 5. The entry it proposes

The entry NTC-0212 proposed, **M1.24** — *the shipped default of a tenant setting that limits
no spending* — covers the first. The second and third are operator settings with a product
default; the entry it proposes is **M1.25** — *the default of an instance setting that limits no
spending and moves no autonomy level*.
