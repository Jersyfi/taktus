# NTC-0224 — A tenant that declared no sources has none free, and the owner decides the export anchor

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-23
**Raised in:** issue [#432](https://github.com/Jersyfi/taktus/issues/432), in the pull request that closes it
**How it follows:** UC-7.7 §2 says an analytic step reads "a source the tenant declares free of personal fields", and that a source not so declared is refused. A tenant that declared nothing has declared no source free; refusing every source is the requirement as written, not a choice. Principle 14 and UC-03 §6 keep user data outside a specific case with a person "at every stage"; the anchor that does so needs a decider before any tenant configures one. The shipped anchors already name the role `owner` for the legal and the correction anchor (`docs/decisions/anchors.md`, ADR-0042), so the frame's own anchor takes the same role. Where a stricter and a looser default were both consistent with the sources, the stricter was taken: nothing is free until declared.

## 1. What was decided

ADR-0130 needs two values before a tenant sets any.

1. **A tenant that declared no sources has no source free of personal fields, and declares no
   capability personal.** No analytic step reads a source until `taktusctl sources declare
   --free` names it. Only a connector's own `scoped` declaration says that a capability serves
   personal data until `--personal` adds one.
2. **The frame's anchor on personal data outside a specific case, `anc-personal-data`, is of
   class `legal` and is decided by the role `owner`.** No tenant configuration changes the
   role yet.

Both are product defaults, not the project's.

## 2. The evidence

- Before this change no step was analytic and no connector declared a capability scoped. The
  defaults therefore change nothing a process did before: every test that ran before runs
  unchanged.
- `tests/components/governance/test_sources.py`
  `test_a_tenant_that_declared_nothing_has_no_free_and_no_personal_source` holds the first.
- `tests/components/run/test_case_scope.py`
  `test_an_analytic_step_on_a_source_not_declared_free_is_refused` shows the first default
  refusing an analytic step.
- `tests/components/run/test_case_scope.py`
  `test_reading_personal_data_outside_a_case_halts_a_level_4_process` shows the anchor raised
  as `legal` at level 4.

## 3. What was considered

- **Every source free unless declared personal.** An analytic step would read any source a
  tenant forgot to declare. UC-7.7 §2 refuses a source not declared free. Rejected.
- **The anchor decided by a role `data-protection`.** No tenant has such a role, and a request
  addressed to a role nobody holds is never answered. Rejected until a tenant can name one.
- **The anchor of class `strategic`.** A strategic anchor may be reduced to nothing
  (ADR-0008). Rejected.

## 4. Which entry permits it

No entry of modes 3 or 4 names a default of a tenant's source declaration or the decider of an
anchor the frame raises. M3.10 names limits on spending, and neither limits spending. No entry
of mode 2 names them either, so M2.6 applies.

## 5. The entry it proposes

The entry NTC-0212 proposed, **M1.24** — *the shipped default of a tenant setting that limits
no spending* — covers both.
