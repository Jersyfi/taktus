# Conformance suite

The contract suite, runnable against a foreign adapter (`docs/architecture/contracts.md` §3),
proven here for both contracts. Each reference adapter is started as a separate process, exactly
as a foreign one would be reached; the suite never imports it.

| File | Proves |
|---|---|
| `test_worker_v1_fixtures.py` | every transcript fixture of the worker contract is known good or known bad by the stream rules |
| `test_worker_v1_reference.py` | the reference worker passes W-01 to W-11 in both profiles; W-12 stays pending |
| `test_worker_v1_faults.py` | for every fault the reference worker can inject, the suite fails on exactly that check |
| `test_connector_v1_rules.py` | the connector rules on known-good and known-bad documents |
| `test_connector_v1_reference.py` | the reference connector passes C-01 to C-09 against the fake service; C-10 stays pending; the fake holds one record per key afterwards |
| `test_connector_v1_faults.py` | for every fault the reference connector can inject, the suite fails on exactly that check |
| `test_taktusctl.py` | `taktusctl conformance run` end to end, for both contracts |

Credential values are random per test and reach the adapters through their environment only;
the honest adapters never write one anywhere, and the suite scans for them.
