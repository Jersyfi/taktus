# NTC-0079 — The maturity threshold binds real runs on integrations

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-09
**Raised in:** issue [#78](https://github.com/Jersyfi/taktus/issues/78)
**How it follows:** `docs/architecture/contracts.md` §3 states the rule for "production processes at autonomy level 3 and above", and NTC-0051 wrote it into UC-7.1 as what a process "uses". A rehearsal is no production run: it acts on nothing outside, every outward operation answers from a recording, and every entry says so (ADR-0030). The loopback connector is no integration: contracts.md §4 says it is "never itself an integration the removal test lists", so it can never earn the removal half that *verified* needs. Holding either to the threshold would not make anything safer; it would stop the removal test, which CLAUDE.md §6 requires weekly and which is the only way any adapter earns *verified*. Strict in substance: every real step on an integration at level 3 is held to *verified*, and an engine that cannot read a maturity record runs none; sparing in ceremony: nothing is added for the two cases that act on nothing outside.

## 1. What was decided

From level 3 a step runs only on an adapter at *verified* or above (NTC-0051). Three readings
were needed to build it:

- **A rehearsal is not held to it**, and is not asked for confirmations at levels 1 and 2 either.
  The removal test rehearses every process that uses an integration, with and without it; a
  rehearsal that waited for a person or was refused its adapter would show nothing about the
  integration.
- **The loopback connector is not held to it.** Taktus reaches itself through it; every operation
  is a read inside the instance. The composition answers it as no integration.
- **No maturity record, no level-3 step on an adapter.** An engine wired without the port refuses
  such a step with the finding; a rule, which needs no adapter, runs.

An adapter nothing has recorded is *experimental*, and the finding says that both halves are
missing.

## 2. The evidence

- `docs/architecture/contracts.md` §3: "Production processes at autonomy level 3 and above may only
  use adapters at *verified* or above." §4, the loopback row: "it is never itself an integration
  the removal test lists".
- ADR-0030: a rehearsal sends no outward call and marks every ledger entry `rehearsal: true`.
- `blueprints/self-operation/processes/S-01-removal-test.yaml` runs at level 3 and calls only
  `orchestrator.*`, served by the loopback. Held to the threshold, it could never run, and no
  adapter could ever earn the removal half.
- `components/catalog/domain/model/maturity.py`: nothing records the conformance half yet (#93),
  so no integration is *verified* today.

## 3. What was considered

- **Holding rehearsals to the levels and the threshold.** Rejected: the removal test would compare
  two runs that stop at the same first step, whatever the integration does.
- **Answering the loopback as *verified* or *reference*.** Rejected: neither half was shown for it;
  calling it what it is — no integration — keeps the record honest.
- **Running level-3 steps when no maturity can be read.** Rejected: that fails open.

## 4. Which entry permits it

No entry of the anchor page names how a requirement's threshold reads for a rehearsal or for the
instance reaching itself. M3.15 keeps what UC-7.1 requires with the owner; these readings change no
word of it and apply it where it has an object. M2.6 applies.

## 5. The entry it proposes

**M1.14** — *How a threshold on adapters reads for a run that acts on nothing outside*: a rehearsal
and the instance's own loopback are outside any rule that guards what an integration does to the
world, as long as they act on nothing outside; recorded in the ADR that builds the rule.
