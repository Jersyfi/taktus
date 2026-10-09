# NTC-0091 — The loopback runs a suite as a write, outside the threshold

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-09
**Raised in:** the pull request of issue #93
**How it follows:** Issue #93 says a process starts the suite "through the loopback connector (ADR-0027)". The connector contract says an operation's effect states whether it leaves the system (`contracts/connector/v1` §3), and a suite's run does leave it: it posts assignments to a worker, calls a model, and writes records into a connector's target. So the operation is declared `write`, with idempotency `none`, which the run never repeats on its own (ADR-0024). NTC-0079 keeps the loopback outside the maturity threshold because the threshold guards what an integration does to the world, and the loopback is no integration. The suite's run is how an adapter earns the conformance half; requiring that half before the run would make it unreachable, as holding S-01 to the threshold would have made the removal half unreachable. Strict in substance: the effect is declared as it is, so a rehearsal answers it from a recording and level 1 proposes it to a person instead of running it; sparing in ceremony: no new exemption, the loopback stays what NTC-0079 says it is.

## 1. What was decided

The loopback connector gains the capability `orchestrator.conformance` with one operation,
`orchestrator.conformance.run`. It takes an adapter identifier and nothing else. The instance runs
that adapter's contract suite against the endpoint its configuration resolves, and records what it
found (ADR-0044).

The operation declares effect `write` and idempotency `none`. It is the first loopback operation
that is not a read. Its result reports the ledger entry `conformance.tested` as the record that
went out, and the digest of the evidence.

The loopback stays outside the maturity threshold. A step at level 3 may call the operation
whatever the maturity of the adapter it tests.

## 2. The evidence

- `contracts/connector/v1` §3: the effect field says whether an operation's effect leaves the
  system. `contracts/connector/v1/CONFORMANCE.md` §3: "The suite writes to your target."
- `src/taktus/conformance/suite.py`: the worker suite posts up to seven assignments and a capacity
  probe; `src/taktus/conformance/model/suite.py` makes two model calls.
- NTC-0079: "The loopback connector is not held to it. Taktus reaches itself through it".
- `docs/architecture/contracts.md` §3: *verified* needs the conformance suite passed.

## 3. What was considered

- **Declaring it `read`, like every other loopback operation.** Rejected: a rehearsal would then
  call it for real, and a step at level 1 would run it instead of proposing it.
- **Holding the operation to the threshold.** Rejected: an adapter below *verified* could never be
  tested through a process, so the conformance half could only be earned by hand.
- **No loopback operation; the command line only.** Rejected: issue #93 names both ways, and a
  process that maintains the instance must be able to run it without a person at a terminal.

## 4. Which entry permits it

No entry of the anchor page names how an operation of the instance reaching itself is declared
when it leaves the system. It breaks no contract (M3.5): the connector contract asks for exactly
this declaration. It moves no limit and no level (M3.9, M3.10). M2.6 applies.

## 5. The entry it proposes

**M1.16** — *How the instance's own operations are declared*: an operation of the loopback
connector declares the effect it has, as any connector's does; one that leaves the system is a
`write` or a `delivery`, and the loopback stays outside the maturity threshold as long as the
operation is how an adapter earns a half of its maturity.
