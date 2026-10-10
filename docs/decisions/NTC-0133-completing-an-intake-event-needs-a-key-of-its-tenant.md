# NTC-0133 — Completing an intake event needs a key of its tenant

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-10
**Raised in:** issue [#189](https://github.com/Jersyfi/taktus/issues/189), in the pull request that closes it

## 1. What was decided

`POST /intake-events/{event_id}/complete` on the `api` role answers only a caller whose account
key proves an identity, as issue #189 requires. Before, it completed the event in whatever
tenant its `tenant` query parameter named, the first configured tenant when it named none,
without a key. Its answer is the command the event became, so anyone who reached the surface
could read it. What the software does differently:

- The request reads the account key from `Authorization: Bearer` and nowhere else. Without a
  key, with one that proves no identity, or with the key in the URL, the answer is `401`, and
  nothing is completed.
- The tenant is the tenant of the caller's identity. The `tenant` query parameter is gone; a
  request that still names one is answered for the caller's own tenant.
- An event of another tenant is answered `404`, as one that does not exist, and stays as it
  was.
- Any identity of the tenant may complete an event. Which roles may do so is UC-7.3, outside
  this change. The command still acts for the identity the sender's account is linked to, never
  for the caller.

The automation role completes intake events in the process, through the same handler, and does
not use this request (ADR-0048). Nothing about it changes. `tools/first_run.sh`, `taktusctl` and
`deploy/docker/verify.sh` do not use the request.

## 2. The evidence

- Issue #189, its sections "How it is verified" and "Where the boundary lies"; ADR-0040 §2,
  which places the account key in `Authorization: Bearer`; ADR-0020 §1.
- `tests/adapters/rest/test_surface.py`: the request is `401` without a key, with an unknown
  key, with another scheme, with the key in two query parameters, and the event is still
  awaiting its identity afterwards. A caller of another tenant receives `404` whatever `tenant`
  the request names, and the event is not completed. The caller of the event's tenant completes
  it as before, `409` the second time.
- `tests/integration/test_event_reactions.py`: the automation role completes events and starts
  their processes as before.

## 3. What was considered

- **Only the identity the sender is linked to may complete the event.** Rejected for now: the
  issue binds the request to the tenant, and who may act for whom inside a tenant is the
  role-based authorisation of UC-7.3. Completion executes nothing; it returns the command for
  whoever commissions a plan from it.
- **Keep `tenant` and refuse a mismatch with `403`.** Rejected for the reason NTC-0132 gives:
  the parameter can only repeat what the key already says.

## 4. Which entry permits it

M2.4, *"A change of what the software does, made inside an agreed scope, that breaks no
contract, moves no limit or autonomy level and says nothing public."* The scope is issue #189.
The HTTP surface (`api/openapi.yaml`) is generated and is no contract under `contracts/`. No
limit or level moves. Nothing is said under the project's name.
