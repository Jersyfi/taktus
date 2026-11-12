# DEC-0233 — A process version read from the database lost its escalation and its heal limit

**Category:** DEFECT
**Raised in:** the second process area of release 1.0 (DEC-0228), while storing the frame of
UC-4.3 (ADR-0255)
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

A process version may declare `escalation` — whom a failure's escalation reaches, by which path
and how soon (ADR-0252) — and `heal_limit`, how often the same failure is healed before it is
said (ADR-0254). The postgres mapper of process versions stores one column per field it knows
(`ProcessVersionMapper` in `src/taktus/adapters/driven/postgres/_mapping.py`). It did not know
these two. A version registered on an instance lost both when it was read back: every
escalation went to the owner through the channel without a time to react, and every limit was
three. The round trip of `tests/adapters/persistence/test_repositories.py` passed, because its
sample version declared neither field: a field left at its default comes back at its default
from a mapper that never stored it. The gate claimed a coverage it did not have.

## 2. Why you are being asked

You are not. A hole in a gate's coverage found on the way is a documentation defect, corrected
here (CLAUDE.md §11 point 11).

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

- **The correction.** Migration `0104` adds the columns `escalation` and `heal_limit` to
  `process_version`, beside the frame and the change record of ADR-0255; the mapper stores and
  reads them.
- **The gate.** The sample version declares every field a version has, and
  `test_the_sample_version_leaves_no_field_at_its_default` fails when a field is added to the
  version and not to the sample, as the bundle's round trip already did for `bundle_of` (#611).
- **Who it affects.** No instance has registered a version with either field: both arrived on
  the concept branch of release 1.0, which has not merged.
- **The gate is stricter, not weaker.** No check was removed or loosened.

## 5. Options

None for the owner.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0233" in an issue.

## Outcome

**Corrected:** 2026-11-07
**What was wrong:** a process version stored in the database came back without its escalation
and its heal limit, and the persistence round trip did not notice.
**Why it was wrong:** the two fields were added to the version and its bundle, and not to the
mapper, whose sample version left them at their defaults.
**What it now says:** the mapper stores both, and the sample declares every field.
**What changed in substance:** nothing that was required; the version is stored as declared.
**Recorded in:** the branch of the second process area of release 1.0 (DEC-0228)
