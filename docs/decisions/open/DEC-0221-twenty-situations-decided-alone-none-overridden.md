# DEC-0221 — Twenty situations decided alone, none overridden

**Category:** NON-BLOCKING
**Raised in:** the pull request for issue #433 (ADR-0132), whose notice NTC-0226 is the twentieth `unlisted` notice; `make gate-decisions` fails the register until this request exists (DEC-0042)
**Issue:** [#604](https://github.com/Jersyfi/taktus/issues/604)
**Needed by:** 2026-11-06
**Provisional answer:** Option A. Sessions go on deciding a situation no anchor names, and record it as an `unlisted` notice; the next review comes at forty.
**Override review:** 20 `unlisted` notices, 0 overridden by a later decision: an override rate of 0 %.

## 1. What this is about

A session sometimes meets a situation that no entry of the anchor page names. Since DEC-0039
it does not ask you then. It decides in the direction the vision and the existing anchors
point, and records the decision as a *notice*: a short record of kind `unlisted` that says
what was decided, from which source and how it follows. You read the notice, and you override
it with a decision where it went the wrong way. This is called the *reversed default*.

You asked, in DEC-0042, not only to see how often you overrode such notices, but to be asked
about it after every twenty. The twentieth was written today, NTC-0226, in the pull request for
issue #433. This is that question.

## 2. Why you are being asked

DEC-0042 makes the review a request to you, after every twenty `unlisted` notices. How much a
session decides alone is yours to set (DEC-0039).

**Sources checked:** `docs/vision/` — principle 9 (efficiency over verbosity) and principle 10
(the autonomy range, with guardrails) point both ways and set no number. The ADRs — ADR-0017 §9
places the review and leaves its outcome to you. Both anchor pages — `anchors.taktus.md`,
section *Neither list*, says that the review happens, not what follows from it. The register —
DEC-0039 and DEC-0042 set up the review; no earlier review exists, since this is the first.

## 3. What you must decide

Whether sessions go on deciding situations that no anchor names, and record each as a notice,
or whether such a situation becomes a question to you again.

## 4. What you need to know to decide

- **The rate.** Twenty `unlisted` notices; none was overridden by a later decision. `make
  status` counts both.
- **What they decided.** Five set the shipped default of a tenant setting: NTC-0212 (the watch
  of expected runs), NTC-0214 (a signal's corridor), NTC-0215 (the correction limits),
  NTC-0217 (routing between models) and NTC-0226 (the limits on repetition, and how often a
  capped run counts again). Four chose the strict reading of an open question: NTC-0088,
  NTC-0096, NTC-0100 and NTC-0224. Two placed a kind of wait in the blocked-time accounts:
  NTC-0090 and NTC-0098. The other nine: NTC-0018 (a session spends up to USD 1 to derive
  instead of asking, since accepted as M2.8), NTC-0049, NTC-0064, NTC-0065, NTC-0079, NTC-0091,
  NTC-0127 (since accepted as M1.20), NTC-0189 and NTC-0216.
- **What a rate of 0 % says.** Either the sessions decide as you would, or the notices are not
  read. The register cannot tell the two apart.
- **A pattern you may want to settle separately.** All five defaults propose the same new
  entry, M1.24: the shipped default of a tenant setting that limits no spending becomes the
  session's, without a notice. That is not decided by this request.

## 5. Options

### Option A — keep the reversed default (recommended)

- **Meaning:** a session goes on deciding a situation that no anchor names, and records it as an
  `unlisted` notice. The next review comes after forty.
- **Consequence:** the work continues without waiting; you read the notices when you choose.
- **Effort:** none.
- **Reversibility:** cheap: a later answer can narrow it at any time.
- **Why recommended:** none of twenty was overridden. Since DEC-0040 a session takes the
  stricter option where two are consistent with the sources, which is what you chose in four of
  the five recommendations you rejected before.

### Option B — such a situation becomes a question again

- **Meaning:** a situation that no anchor names becomes a `NON-BLOCKING` decision request, and
  the work continues on its provisional answer, as before DEC-0039.
- **Consequence:** you are asked about every such situation; about one request in every other
  pull request, at the pace of the last twenty.
- **Effort:** the anchor pages, CLAUDE.md §8 and the gate.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing. The work continues on Option A.

## 7. How to answer

"DEC-0221: Option A." or "DEC-0221: Option B."
