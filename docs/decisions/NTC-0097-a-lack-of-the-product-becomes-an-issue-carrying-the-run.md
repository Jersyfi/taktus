# NTC-0097 — A lack of the product becomes an issue carrying the run

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-09
**Raised in:** issue [#86](https://github.com/Jersyfi/taktus/issues/86), in the pull request that closes it

## 1. What was decided

An instance now reports what it met that the product lacks (UC-6.12, ADR-0046). What the software
does differently:

- A step that fails because no configured worker offers its capabilities, no configured connector
  serves its capability, or the connector does not offer its operation, carries a block from the
  failure. The block's cause is `no_worker`, `no_connector` or `operation_unsupported`, it names
  what was lacking, and it is booked to `wait.dependency`. The step still fails and its run still
  escalates (NTC-0002). When a retry finds the adapter, the block ends with its record.
- `BlockedTime` also reads the blocks that have not ended.
- The new `reporting` component makes a finding of every such block and of nothing else, one per
  lack. Where `TAKTUS_FINDINGS_CONNECTOR` is set, the scheduler sends the findings every ten
  minutes to the Taktus repository: an issue in the shape of the form `Task`, and a comment for
  every later occurrence or end, the waiting summed. Every text sent is a `finding.sent` entry in
  the ledger.
- `taktusctl findings` shows every finding the instance recorded, ready to send by hand.

## 2. The evidence

- UC-6.12 §2, in force provisionally under DEC-0087, and issue #86, which states how it is
  verified.
- `tests/adapters/connectors/test_product_findings.py` meets one lack twice against the fake
  repository service and finds one issue with two occurrences and the waiting summed, and finds no
  person, no content and no secret in any text.
- `tests/components/run/test_blocked_time.py::test_a_lack_of_an_adapter_is_a_block_that_lasts_until_the_step_can_start`
  shows each of the three lacks booked, kept across a retry, and ended once the step starts.

## 3. What was considered

- **Send the finding when the block ends.** Rejected: a lack nobody repairs never ends, and the
  product would never hear of it.
- **Send on every scheduler tick.** Rejected: each sending reads the repository's issues, and a
  tick a second would spend the service's rate limit on nothing new.
- **Send by default on every instance.** Rejected: UC-6.12 §2 lets an instance outside the Taktus
  project send only where its operator enabled it, and the repository is public.

## 4. Which entry permits it

M2.4, *"A change of what the software does, made inside an agreed scope, that breaks no published
contract, moves no limit or autonomy level and says nothing public."* The scope is issue #86. No
schema under `contracts/` changes: the block's `lacking` is a field of the run's own model, and the
connector operations used exist. No limit and no level moves. Nothing is said publicly under the
project's name by this change: an instance sends only where its operator set the connector, and
what it sends is a task in the project's own backlog.
