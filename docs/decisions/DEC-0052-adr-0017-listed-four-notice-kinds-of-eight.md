# DEC-0052 — ADR-0017 listed four notice kinds of eight

**Category:** DEFECT
**Raised in:** [#59](https://github.com/Jersyfi/taktus/pull/59), while adding the kind `spend` (DEC-0049)
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

Every notice carries a kind, one word from a vocabulary the shipped anchor page defines. ADR-0017
§2a named the vocabulary as four words: `restructuring`, `test-strategy`, `gate-weakened`,
`behaviour-change`. Since 2026-09-21 the vocabulary also holds `need`, since 2026-10-01 `unlisted`
and `restoration`, and since 2026-10-07 `spend`. A reader of the ADR would have taken a notice of
kind `unlisted` for a fault.

## 2. Why you are being asked

You are not. The repository says something that is not so, which is entry M1.4 of
`docs/decisions/anchors.taktus.md`.

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

- The ADR now says that the vocabulary is the shipped default's, kept in `anchors.md` §1 and
  nowhere else, so that a new kind changes one file.
- The gate never read the ADR's list; it reads the anchor pages. Nothing was enforced wrongly.

## 5. Options

None for the owner.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0052" in an issue.

## Outcome

**Corrected:** 2026-10-07
**What was wrong:** ADR-0017 §2a listed four kinds; the vocabulary has eight.
**Why it was wrong:** three kinds were added to `anchors.md` by later decisions without the ADR's
copy of the list being changed; a list kept in two places drifted.
**What it now says:** the vocabulary is `anchors.md` §1, kept there and nowhere else.
**What changed in substance:** nothing; the gate reads the anchor pages.
**Recorded in:** [#59](https://github.com/Jersyfi/taktus/pull/59)
