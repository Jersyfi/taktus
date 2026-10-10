# NTC-0132 — The read API answers an authenticated reader

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-10
**Raised in:** issue [#186](https://github.com/Jersyfi/taktus/issues/186), in the pull request that closes it

## 1. What was decided

The read API of the `api` role answers only a reader whose account key proves an identity, as
ADR-0055 §5 and issue #186 require. The three requests are `GET /runs`, `GET /runs/{run_id}`
and `GET /runs/{run_id}/ledger`. Before, each answered for whatever tenant its `tenant` query
parameter named, the first configured tenant when it named none, without a key. What the
software does differently:

- Each request reads the account key from `Authorization: Bearer` and nowhere else. Without a
  key, with one that proves no identity, or with the key in the URL, the answer is `401`, an
  RFC 9457 problem that says nothing about what exists.
- The tenant is the tenant of the reader's identity. The `tenant` query parameter is gone; a
  request that still names one is answered for the reader's own tenant.
- Each request asks the reporting component's visibility predicate,
  `components/reporting/domain/service/visibility.py`, for every run it would show. The stream
  of changes asks the same function. Every caller calls it through its module, so that no path
  holds a copy of the rule. Until UC-6.4 the predicate is the tenant boundary.
- A run the reader may not see is answered `404`, exactly like a run that does not exist.

`deploy/docker/verify.sh` adds an identity with `taktusctl identity add`, issues it a key with
`taktusctl identity key`, checks that `GET /runs` refuses a request without it, and reads with
it. `tools/first_run.sh` and `taktusctl` do not use the read API and are unchanged.

## 2. The evidence

- Issue #186, its sections "How it is verified" and "Where the boundary lies"; ADR-0055 §5;
  ADR-0040 §2, which places the account key in `Authorization: Bearer`.
- `tests/adapters/rest/test_reads.py`: each of the three requests is `401` without a key, with
  an unknown key, with another scheme, with the key in four query parameters and with a retired
  key; a reader sees their own tenant's run and not another tenant's, whatever `tenant` the
  request names, and the other tenant's reader the other way round; with the predicate replaced
  by one that withholds some of the reader's own runs, the three requests and the snapshot of
  `GET /changes` show exactly the same runs.
- `tests/adapters/rest/test_surface.py` and `tests/integration/test_daemon_shutdown.py` read with
  a key; the latter checks the `401` on a served daemon.

## 3. What was considered

- **Keep `tenant` and refuse a request that names another tenant with `403`.** Rejected: the
  parameter can only ever repeat what the key already says, and a `403` for a tenant that does
  not exist and one that does would have to be told apart or made the same. Without the
  parameter there is nothing to compare.
- **Answer a withheld run with `403`.** Rejected: it would tell the reader that the run exists.
  ADR-0055 §5 makes a withheld change absent, not replaced; a read follows the same rule.
- **Move the read API into a query object of `reporting`.** Rejected for now: the adapter
  already holds the run repository it reads, and the rule it applies is one function call. The
  rule stays in `reporting`; only the call is in the adapter.

## 4. Which entry permits it

M2.4, *"A change of what the software does, made inside an agreed scope, that breaks no
contract, moves no limit or autonomy level and says nothing public."* The scope is issue #186
under ADR-0055 §5. The HTTP surface (`api/openapi.yaml`) is generated and is no contract under
`contracts/`; no contract changes. No limit or level moves. Nothing is said under the project's
name.
