# Conformance suite

The contract suite, runnable against a foreign adapter (`docs/architecture/contracts.md` §3),
proven here for both contracts. Each reference adapter is started as a separate process, exactly
as a foreign one would be reached; the suite never imports it.

| File | Proves |
|---|---|
| `test_worker_v1_fixtures.py` | every transcript fixture of the worker contract is known good or known bad by the stream rules, every capacity probe by the capacity rule (W-15), every unknown-id and repeated-id probe by the id rules (W-16, W-17); the transcripts `W-18-*` by the rule of the command after the work |
| `test_worker_v1_reference.py` | the reference worker passes W-01 to W-11 and W-13 to W-18 in both profiles — for W-15 the suite holds its four places and gets `503` for a fifth; for W-16 an id never posted gets `404`; for W-17 an id repeated while it runs and after it finished gets `409`; for W-18 a command after the work comes back as its artifact byte for byte, and one that exits with 1 fails the assignment; W-12 stays pending; a suite that fills fewer places than it declares leaves W-15 inconclusive; started to underestimate, it halts at a limit equal to its estimate; a worker that never exceeds its estimate leaves W-14 inconclusive |
| `test_worker_v1_faults.py` | for every fault the reference worker can inject, the suite fails on exactly that check — run the way the instance runs it, and recorded as not passed with exactly that check (ADR-0044, NTC-0092) |
| `test_worker_v1_coding.py` | the coding worker against the fake agent passes the same checks in both authentication modes and fails exactly the check of each fault; a token limit halts it at a boundary and the resume continues; an expired session and an exhausted window halt it too |
| `test_connector_v1_rules.py` | the connector rules on known-good and known-bad documents |
| `test_connector_v1_reference.py` | the reference connector passes C-01 to C-09 against the fake service, with a token and as Taktus's own app (ADR-0033); C-10 stays pending; the fake holds one record per key afterwards; as the app, no token the fake issued and no statement the connector signed appears in the report or the log — the suite's C-04 cannot know them |
| `test_connector_v1_faults.py` | for every fault the reference connector can inject, the suite fails on exactly that check — run the way the instance runs it, and recorded as not passed with exactly that check (ADR-0044, NTC-0092); the app serving a call without a credential fails C-03 |
| `test_recorded.py` | the instance runs the suite against the adapter its configuration resolves and records it: the reference worker, the reference connector with its scenario against the fake service, and the model adapter against the fake endpoint recorded as passed under the configuration each declares; the endpoint ignoring the output limit recorded as failing M-03, one that does not answer as not passed; a connector without a scenario, the database and an identifier nothing is configured under run and record nothing |
| `test_connector_v1_chat.py` | the chat connector passes C-01 to C-09 against the fake chat service under the timestamped signature scheme, C-10 pending; the fake holds one message per key afterwards; for every fault the chat connector can inject — `C-08-stale` and `C-08-handshake` among them — the suite fails on exactly that check |
| `test_taktusctl.py` | `taktusctl conformance run` end to end, for both contracts; `taktusctl conformance record` end to end against the reference worker, the person who ran it the actor |

Credential values are random per test and reach the adapters through their environment only;
the honest adapters never write one anywhere, and the suite scans for them.
