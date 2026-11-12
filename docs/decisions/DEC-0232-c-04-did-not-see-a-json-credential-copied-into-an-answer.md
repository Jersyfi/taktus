# DEC-0232 — C-04 did not see a credential of JSON copied into an answer

**Category:** DEFECT
**Raised in:** the contact area of release 1.0 (DEC-0228), while building the two connectors that
authenticate with a service account's key file (ADR-0207, ADR-0209)
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

The connector suite's check C-04 proves that no credential value reaches an answer or a log
(`contracts/connector/v1`). It looked for the value in clear, in base64, and with its line
breaks escaped (`needles_of` in `src/taktus/conformance/connector/suite.py`). A credential that
is itself a JSON document — a service account's key file — holds quotes and backslashes. A JSON
answer that copies it writes them escaped, so none of the three needles matched. The suite
passed a connector whose fault `C-04-result` copied the key file into every answer. The gate
claimed a coverage it did not have.

## 2. Why you are being asked

You are not. A hole in a gate's coverage found on the way is a documentation defect, corrected
here (CLAUDE.md §11 point 11).

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

- **The correction.** `needles_of` also looks for the value as a JSON string writes it, where
  that differs from the value. A test in `tests/conformance/test_connector_v1_rules.py` proves
  the needle is found.
- **Who it affects.** Only connectors whose credential holds a quote or a backslash: the second
  app store's and the workspace audit connector's key files. Every earlier connector's
  credential is a plain token, which the earlier needles already found.
- **The gate is stricter, not weaker.** No check was removed or loosened.

## 5. Options

None for the owner.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0232" in an issue.

## Outcome

**Corrected:** 2026-11-07
**What was wrong:** the connector suite's check C-04 claimed that no credential value reaches an
answer, and did not find a credential of JSON that an answer copied.
**Why it was wrong:** its needles were written when every credential was a plain token, which
JSON writes unchanged.
**What it now says:** C-04 also looks for the value as a JSON string writes it.
**What changed in substance:** nothing that was required; the check now holds what it claimed.
**Recorded in:** the branch of the contact area of release 1.0 (DEC-0228)
