# Conformance suite

The contract suite, runnable against a foreign adapter (`docs/architecture/contracts.md` §3),
proven here for both contracts. Each reference adapter is started as a separate process, exactly
as a foreign one would be reached; the suite never imports it.

| File | Proves |
|---|---|
| `test_worker_v1_fixtures.py` | every transcript fixture of the worker contract is known good or known bad by the stream rules, every capacity probe by the capacity rule (W-15) |
| `test_worker_v1_reference.py` | the reference worker passes W-01 to W-11 and W-13 to W-15 in both profiles — for W-15 the suite holds its four places and gets `503` for a fifth; W-12 stays pending; a suite that fills fewer places than it declares leaves W-15 inconclusive; started to underestimate, it halts at a limit equal to its estimate; a worker that never exceeds its estimate leaves W-14 inconclusive |
| `test_worker_v1_faults.py` | for every fault the reference worker can inject, the suite fails on exactly that check |
| `test_worker_v1_coding.py` | the coding worker against the fake agent passes the same checks in both authentication modes and fails exactly the check of each fault; a token limit halts it at a boundary and the resume continues; an expired session and an exhausted window halt it too |
| `test_connector_v1_rules.py` | the connector rules on known-good and known-bad documents |
| `test_connector_v1_reference.py` | the reference connector passes C-01 to C-09 against the fake service, with a token and as Taktus's own app (ADR-0033); C-10 stays pending; the fake holds one record per key afterwards; as the app, no token the fake issued and no statement the connector signed appears in the report or the log — the suite's C-04 cannot know them |
| `test_connector_v1_faults.py` | for every fault the reference connector can inject, the suite fails on exactly that check; the app serving a call without a credential fails C-03 |
| `test_taktusctl.py` | `taktusctl conformance run` end to end, for both contracts |

Credential values are random per test and reach the adapters through their environment only;
the honest adapters never write one anywhere, and the suite scans for them.
