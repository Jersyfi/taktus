# DEC-0003 — Where the stream rules live

**Category:** NOTE
**Raised in:** [#1](https://github.com/Jersyfi/taktus/pull/1), as open point 3 of its description, listed among the items to "confirm or redirect"
**Issue:** none; raised before ADR-0017, in the description only

This record is the worked example of ADR-0017 §3, category NOTE: information that was presented
as if it needed an answer. It is kept in the register because asking about non-decisions trains a
reader to stop reading, and the pattern should be recognisable next time.

## 1. What this is about

The worker contract — how Taktus hands work to an external program and receives its progress —
has twelve *conformance checks*, numbered W-01 to W-12. They describe what a correct worker does:
number its events without gaps, report what it consumed after every step, refuse a tool it was
not allowed, and so on. Some of these can be expressed in the schema language itself; seven
cannot, because they are about the sequence of events, not the shape of one. For those seven the
first pull request wrote a small piece of code, the *stream rules*, inside the tool that validates
the contracts, so that the example transcripts in the repository can be proven good or bad.

The pull request then noted that these rules would probably move into the conformance suite — the
test suite that runs against a live worker — once that suite exists, and listed the note under the
items the reader should confirm or redirect.

## 2. Why you are being asked

You are not. No row of `anchors.md` §1 applies. Where a piece of code lives inside the documented
structure is row D1 of §2, *naming, file placement, module layout* — decided by the session and
recorded. That the code will later move is row D5, *how to sequence work inside an agreed scope*.
Nothing here touches scope, a feature, a version, an ADR, a release, licensing, anything public,
a dependency or a gate.

## 3. What you must decide

Nothing. There was no question in the item, only a statement of where the code is and where it is
expected to go. Presented among items to "confirm", it asked the owner to read and approve a
placement that was theirs neither to approve nor to refuse.

## 4. What you need to know to decide

- **Conformance check.** One of twelve numbered statements in `contracts/worker/v1/README.md`
  about what a correct worker does. Each has at least one example in the repository that must
  fail it, so the check is exercised, not just written.
- **Stream rule.** The executable form of a conformance check that cannot be expressed as a
  schema, currently a function in `tools/validate_contracts.py`.
- **Conformance suite.** The tests under `tests/conformance/` that will run against a live worker.
  Planned for `0.1.0`; the directory exists and reports "no targets yet".
- **Why it is a note and not a decision.** Whichever file holds the rules, every check is
  exercised, every example still validates, and nothing a third party sees changes. A placement
  that changes nothing observable is never the owner's call.

## 5. Options

None were offered in #1, and none exist for the owner. For the record, what the session decided:
the rules stay in the validator until the conformance suite exists, and the suite becomes the one
place where they live, with the validator importing them. Recorded here, and in the validator's
own documentation, as the plan.

## 6. What is blocked

Nothing. Nothing waited on this item, then or now.

## 7. How to answer

Nothing to answer. If the placement turns out to matter — for example because a third party
needs the stream rules as a separate, importable file — that is a feature request, row O2, and
would be raised as one.

## Outcome

**Recorded:** 2026-09-15
**Why this is a note:** it stated a placement and a plan and asked for nothing. Placement inside
the documented structure and the sequencing of work are the session's to decide and record
(`anchors.md` §2, rows D1 and D5). Listing it among items to confirm put a non-decision in front
of the owner, next to a decision that needed them.
**Recorded in:** [#3](https://github.com/Jersyfi/taktus/pull/3); the mechanism that keeps notes
apart from questions is [ADR-0017](../adr/ADR-0017-decision-requests-in-the-repository.md) §3
