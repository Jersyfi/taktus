# NTC-0246 — A skill is approved automatically after eleven passed rounds, and twenty-two for an exact step

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-30
**Raised in:** issue [#646](https://github.com/Jersyfi/taktus/issues/646), on the branch `concept/package-b` that builds `0.6.0` (DEC-0222)
**How it follows:** DEC-0028 (Option A, the owner's answer) requires a floor for n that no configuration can go below, set when `0.6.0` is designed, from the evaluation data of `0.5.0`, and higher for skills used by `exact` steps. The owner decided that there is a floor and how it is found; this notice applies that answer and sets the number. The data the answer names holds no fallback of any skill, because no skill existed before `0.6.0`. What the data of `0.5.0` does hold is the rule by which one evaluation passes (ADR-0134 §4) and the tolerance it passes within (NTC-0228). The number is derived from that rule as a probability bound. Where two values were both consistent, the stricter in substance was taken (CLAUDE.md §8).

## 1. What was decided

A tenant's skill policy (ADR-0162 §4) ships with:

1. **`floor`: 11.** At autonomy level 4, a skill no `exact` step uses is approved automatically
   only once its eleven most recent rounds all passed.
2. **`exact_factor`: 2.** For a skill an `exact` step uses, the floor is 22.
3. **No lower value.** A policy with a floor below 11 or a factor below 2 is refused. So is a
   tenant's own `n` below the floor; a skill an `exact` step uses then needs `n` times the
   factor. A higher value is accepted.

The values are product defaults, not the project's.

## 2. The evidence

**What the data of `0.5.0` holds.** No skill ran in `0.5.0`, so no data says how often a
skill that passed k evaluations fell back later. That is the measure DEC-0028 §5 names. The
shipped bundles and blueprints declare no evaluation cases (`grep -r scorers blueprints
examples` finds only the documentation). The tenants' recorded evaluations are their own data
and do not enter the repository (DEC-0222). What `0.5.0` fixed is how one evaluation decides:

- An evaluation passes when the candidate's mean score is not below the comparison's by more
  than the tenant's tolerance, 0.05 by default (ADR-0134 §4, NTC-0228).
- A rule scorer gives the same score for the same answer. Two evaluations on the same cases
  differ only where a model answers differently (ADR-0134 §2 and "Where this promise ends").
  So the verdicts of repeated rounds are repeated samples of one question: does this skill,
  this time, stay within the tolerance?

**The bound.** Let p be the share of rounds a skill fails. The chance that it passes n rounds
in a row is (1 − p)^n. The floor is the smallest n for which that chance is at most α.

- **Which skill must not slip through.** A skill that fails one round in four, p = 0.25, has
  failed its own cases often enough that a person must look at it.
- **How sure.** α = 0.05, the convention for a test of one claim, which no source of the
  repository sets otherwise.
- n ≥ ln 0.05 / ln 0.75 = 10.41, so **n = 11**: 0.75^11 = 0.042. Ten would give 0.056, above
  α.

**For an `exact` step.** The factor 2 doubles the rounds. At the same α it catches a skill
that fails about half as often: 0.87^22 = 0.047, so a skill that fails one round in eight
slips through at most one time in twenty. For the skill of one round in four, the chance
falls to 0.75^22 = 0.0018. An `exact` step is where a wrong value has no exception (CLAUDE.md
§4). A skill never produces that value, but the person or the rule that does reads what the
skill prepared (DEC-0028 §4).

**What it costs.** At level 4 a round starts at most once a day (ADR-0162 §4). Eleven rounds
are at least eleven days, twenty-two at least twenty-two. That is shorter than the month of
quality history several shipped processes name for a raise of their level
(`blueprints/dev-orchestration/processes/P-01-roadmap-control.yaml`,
`blueprints/self-operation/processes/S-01-removal-test.yaml`).

**The tests.** `tests/components/catalog/test_skills.py`
`test_the_floor_and_its_exact_factor_are_configuration_and_a_lower_value_is_refused` and
`test_level_four_approves_by_rule_after_n_passed_rounds_and_a_failure_resets`.

## 3. What was considered

- **Option B of DEC-0028, a round number such as 20, fixed now.** Rejected: the owner chose A,
  a number that rests on something measured.
- **The rule of three (n ≥ 3 / tolerance, so 60).** Rejected: it reads the score tolerance as
  a share of failed rounds, two different quantities.
- **p = 0.5, a skill that fails as often as it passes.** It gives n = 5. Rejected as less
  strict: a skill that fails one round in three would pass five rounds in a row one time in
  eight.
- **Waiting for data of skills.** Rejected: DEC-0028 requires the floor to exist when `0.6.0`
  is built. The number can rise later, by a change of the shipped default; it can never fall
  below 11 by configuration.

## 4. Which entry permits it

No entry of modes 3 or 4 names the value of a floor the owner already decided to have. M3.9
names raising an autonomy level; the floor raises none, and the owner answered M3.9's question
in DEC-0028. M1.24, proposed by NTC-0212, names the shipped default of a tenant setting that
limits no spending; a floor that limits an approval is stricter than that. No entry of mode 2
names it, so M2.6 applies.

## 5. The entry it proposes

**M2.10** — *The value of a threshold or floor whose existence and source the owner already
decided, derived from the source the decision names and recorded with the derivation.* Mode 2,
because the owner set the rule and the session only computes it.
