# ADR-0044 — The instance records the conformance half it measured

**Status:** accepted · builds the conformance half of maturity *verified* into the catalog

## Context
An adapter is *verified* when two halves have passed: its contract's conformance suite and the
removal test (`docs/architecture/contracts.md` §3). Since #153 a step at autonomy level 3 runs
only on a *verified* adapter (ADR-0039). The removal half is recorded by S-01 (ADR-0030). The
conformance half had a field in the maturity record, `conformance_passed_at`, and nothing wrote
it. So no adapter could reach *verified*, and every real run of P-01, P-02 and P-03 halted at its
first step on an integration.

Issue #93 asked three questions. Who runs the suite? Against which version? How does a run read
the result? It also set one rule: the half has exactly one writer.

## Decision

### 1. The instance runs the suite itself, against the endpoint its configuration resolves
The suite is the code under `src/taktus/conformance/`. The instance runs it against the endpoint
that its own configuration resolves for an adapter identifier. A caller names the identifier and
nothing else.

- `worker.endpoint`: the configured worker endpoint. A launched kind (`worker.process`,
  `worker.container`, `worker.cluster`): one execution unit started for the suite through the
  execution port, at autonomy level 1, with no host, and ended after it.
- `connector.<label>`: the URL `TAKTUS_CONNECTORS` maps the label to. The suite needs a scenario.
  The instance reads its path under `conformance.connector.<label>.scenario`.
- `model.endpoint`: the configured endpoint and model name, with the declaration the model adapter
  makes for them.

The credential values the suite searches for (W-08, C-04) are read as an execution adapter reads
a credential: under `credential.<name>`. They stay in memory.

A person starts a run with `taktusctl conformance record <identifier>`. A process starts one
through the loopback connector's operation `orchestrator.conformance.run` (ADR-0027). The actor
in the ledger is whoever started it. A report produced elsewhere is never recorded. It would be
asserted rather than measured, and it could not show which endpoint and version it came from.

### 2. A run names the configuration it was taken under
The record names the contract and its version (`worker/v1`), the Taktus version whose suite ran,
and the configuration: the adapter identifier, what the adapter declared and the version it
declared. For a model the version is the model name it is configured with. This is the same shape
as a removal verdict's configuration (ADR-0030 §5). Both are read by one function,
`Pools.configuration`.

### 3. One writer, one transaction
The catalog's `RunConformanceHandler` is the only code that builds the conformance half. Its
command names the adapter, the actor and the run that started it. It takes no report, no verdict
and no date. It runs the suite through the catalog's `Suites` port, which the composition root
implements.

The outcome is read from the report's checks, the way `Report.conformance` computes it. `passed`
means no check failed and none was inconclusive. A `pending` check (W-12, C-10) does not count
against it. A run that ends `failed` or `incomplete` is recorded too, as not passed, and names
the checks that failed or were inconclusive.

The evidence is one document: the report together with the configuration. It is stored in the
object store. Then one transaction writes two things. The first is the ledger entry
`conformance.tested`. Its `outcome` is the outcome, its `content_digest` the digest of the
evidence, and its references name the actor and the run. The second is the conformance half of
the adapter's maturity record (`adapter_maturity.conformance`, migration 0019). The removal half
stays as it was, and the removal handler keeps the conformance half the same way.

### 4. A pass counts only for the configuration it names
The run reads the standing through its maturity port, as before (ADR-0039). The composition root
answers from the record and compares the configuration the pass names with the configuration the
run's own pools resolve for the identifier now. If they differ, the adapter is *experimental*, and
`missing` says the pass was for another configuration and how it differs. The same identifier can
name another adapter tomorrow (#36).

### 5. The loopback's suite operation leaves the system and stays outside the threshold
Running a suite leaves the system: it posts assignments to a worker, calls a model and writes
through a connector into the scenario's target. The operation therefore declares effect `write`
and idempotency `none`, so a run never repeats it on its own. The loopback connector stays outside
the maturity threshold (NTC-0079), because a suite's run is how an adapter earns the conformance
half and cannot require that half first. NTC-0091 records the reasoning.

## Alternatives
- **Accept a report run elsewhere, signed or not.** It is what a person could already do by hand.
  It cannot show which endpoint and version it came from, and a maturity would rest on an
  assertion. The open proposal for UC-10.2 says a maturity cannot be set by hand (DEC-0087).
- **A pass that expires after a time.** A pass is about a configuration, not a date. A change
  behind the identifier invalidates it at once; a date would invalidate a pass that still holds and
  keep one that does not. Re-running the suite periodically is a schedule, not part of this.
- **Count a `pending` check against a pass.** W-12 and C-10 are the removal test, which the other
  half records. Counting them would make the conformance half unreachable by design (DEC-0005).
- **Declare the loopback's suite operation `read`.** It would be wrong: a connector suite writes
  records into its target. The declaration is what a rehearsal and level 1 rely on.

## Consequences
- The catalog gains `ConformanceResult`, the port `Suites` and the handler `RunConformanceHandler`.
  `AdapterMaturity.maturity` and `.missing` take the configuration that resolves the identifier
  now.
- Ledger kind `conformance.tested`. Column `adapter_maturity.conformance`, migration 0019.
  `conformance_passed_at` is now written from it and never read.
- `taktusctl conformance record`. The loopback capability `orchestrator.conformance` with its one
  operation.
- Configuration keys `conformance.worker.task`, `.hosts`, `.credential`, `.log`,
  `conformance.connector.<label>.scenario`, `.log`, `conformance.timeout` and
  `conformance.idle.timeout`.
- The suite's meta-tests run the way the instance runs them, and every fault is recorded as not
  passed (NTC-0092).
- Running the connector suite on Taktus's own instance needs a target it may write to. That is
  NEED-0019.

## Where this promise ends
The record shows what the suite found when the instance ran it. It does not show that the adapter
still behaves so. A pass stays valid until the configuration behind its identifier changes, with
no expiry by time. The configuration compared is what the instance's pools read from the adapter.
The pools read a worker's or a connector's declaration once and keep it. A change behind an
endpoint that the instance has not read again — a worker upgraded while the instance runs — is
seen at the instance's next start, not before. An adapter that declares the same capabilities and
version while behaving differently is not told apart. The Taktus version is the installed
package's version, which does not change between unreleased builds. The suite's checks are what
they are: W-12 and C-10 stay pending, and no check is new. A connector suite writes into whatever
target its scenario names; that the target is a sandbox is the operator's configuration, not
something the suite can see. The instance runs no suite on a schedule. *reference* is not derived.
The removal half's own configuration is not compared with the configuration now; that half is #90.
