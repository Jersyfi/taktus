# NTC-0267 — The connector suite finds a key document quoted in JSON

**Mode entry:** M2.2
**Kind:** test-strategy
**Decided:** 2026-11-07
**Raised in:** the branch `area/release` of `concept/release-1-0` (DEC-0228), for issues #438 and #440

## 1. What was decided

C-04 of the connector suite looks for every credential value it knows in everything it saw and in
the connector's log (`src/taktus/conformance/connector/suite.py`, `needles_of`). It now also
looks for a value as a JSON text quotes it, and for each line of a multi-line member of a value
that is itself a JSON document — a private key inside a service account key. The business
connectors' test (`tests/conformance/test_connector_v1_business.py`) asserts the same for the
honest run. Its search for the secret half of a value split at its colon is kept for the key
pairs it was written for, and no longer splits a JSON document's text.

## 2. The evidence

- A service account key and an app store key are JSON documents with quotes and escaped line
  breaks (ADR-0210, ADR-0211). A result that copies one into its output carries it with every
  quote escaped, so neither the clear nor the base64 form is found: the fault C-04-result passed
  the suite unseen on the first Google connector, before this change.
- With the change, `test_a_fault_fails_exactly_its_check` fails C-04 on the fault and nothing
  else, for every business connector, and every honest run passes (180 tests).
- Split at its colons, a key document's text gives fragments such as an address of the fake
  that the report rightly names; the split now runs only for a pair.

## 3. What was considered

- **Pass such credentials to the suite pre-escaped.** Rejected: the suite would depend on the
  harness knowing how each connector's output quotes, and an operator's own run would miss it.
- **Decode every JSON text the suite saw before searching.** Rejected: a log line is not JSON,
  and the needle covers both.

## 4. Which entry permits it

M2.2 of `docs/decisions/anchors.taktus.md`: a change of test strategy and what the tests now
cover. The gate is strictly stronger; nothing it found before goes unfound.
