# Architecture decisions

Every decision with its context, the alternatives rejected and its consequences. An architectural
change arrives as an ADR, not as a pull request without context. Where code and an ADR disagree, the
ADR wins.

**Every ADR that makes a promise states where the promise ends.** A promise without a stated
boundary reads as a guarantee, and that is where the disappointments come from that a product
never recovers from: ADR-0005 said no limit is ever breached, and a currency limit could be;
ADR-0014 said `exact` is machine-checkable, and did not say that somebody has to write the check.
Both boundaries were documented somewhere other than where the promise was made. Hence the
section `## Where this promise ends`, last in the file, mandatory in every ADR whose prose
promises — `make gate-adrs` (`tools/check_adrs.py`) fails an ADR that promises without
bounding. The section states the boundary; it does not point at it.

| ADR | Title | Status |
|---|---|---|
| [0001](ADR-0001-language.md) | Python as the single server-side language | accepted |
| [0002](ADR-0002-dependencies.md) | Dependencies and the execution environment | accepted |
| [0003](ADR-0003-adapter-obligation.md) | The adapter obligation, enforced in CI | accepted, extended by 0030 (a fourth verdict) |
| [0004](ADR-0004-method-selection.md) | Method selection: which kind of AI per step | accepted |
| [0005](ADR-0005-step-atomicity.md) | Step atomicity and admission control | accepted, amended (DEC-0012), amended 2026-09-30 (DEC-0035) |
| [0006](ADR-0006-ledger.md) | The ledger as a content-free hash chain | accepted |
| [0007](ADR-0007-worker-contract.md) | Worker contract over HTTP and SSE | accepted |
| [0008](ADR-0008-decision-request.md) | Decision requests and strategic anchors | accepted, extended by 0022 |
| [0009](ADR-0009-adapter-monorepo.md) | Adapters in the main repository until 1.0.0 | accepted |
| [0010](ADR-0010-accounting.md) | The Takt as a unit of orchestrated work | **proposed**, amended 2026-09-30 |
| [0011](ADR-0011-process-bundles.md) | Process bundles, optionally mirrored to Git | accepted |
| [0012](ADR-0012-licensing.md) | Licensing and repository visibility | **open — owner decides** |
| [0013](ADR-0013-business-critical.md) | Taktus is business-critical: what follows | accepted |
| [0014](ADR-0014-exactness.md) | Exactness classes | accepted, amended by 0018 |
| [0015](ADR-0015-bottlenecks.md) | Measure waiting, report the marginal value of a change | accepted, amended 2026-10-09 (ADR-0043) |
| [0016](ADR-0016-explicit-architecture.md) | Explicit Architecture: cut by component | accepted, amended by 0029 |
| [0017](ADR-0017-decision-requests-in-the-repository.md) | Decision requests as a repository mechanism | accepted, amended by 0021, extended by 0028, amended 2026-09-29 (§7) |
| [0018](ADR-0018-exactness-applies-to-result-producing-steps.md) | Exactness classes apply to result-producing steps only | accepted |
| [0019](ADR-0019-contract-identity.md) | Contract identity | accepted |
| [0020](ADR-0020-tenants-and-instances.md) | Tenants and instances are different boundaries | accepted |
| [0021](ADR-0021-failure-result-defect-incident.md) | Failure, result defect, incident | accepted |
| [0022](ADR-0022-retroactive-correction-is-anchored.md) | Retroactive correction is anchored by default | accepted |
| [0023](ADR-0023-automatic-emergency-stop-is-rule-based.md) | An automatic emergency stop is rule-based | accepted |
| [0024](ADR-0024-connector-contract.md) | Connector contract on MCP: two directions, a declared effect, an honest repeat | accepted |
| [0025](ADR-0025-where-an-instance-may-run.md) | Where an instance may run | accepted |
| [0026](ADR-0026-autonomy-carries-its-reason.md) | Autonomy carries its reason | accepted |
| [0027](ADR-0027-taktus-reaches-itself-through-the-connector-port.md) | Taktus reaches itself through the connector port | accepted, extended by 0030 |
| [0028](ADR-0028-what-the-owner-must-act-on-becomes-a-record.md) | What the owner must act on becomes a record: needs requests and the status report | accepted, amended 2026-09-30 (DEC-0021) |
| [0029](ADR-0029-views-are-a-component-enablement-is-not.md) | Views are a component; enablement is not | accepted |
| [0030](ADR-0030-a-rehearsal-acts-on-nothing-outside.md) | A rehearsal acts on nothing outside; a removal verdict says what it was taken under | accepted |
| [0031](ADR-0031-taktus-watches-the-platform-it-runs-on.md) | Taktus watches the platform it runs on | accepted |
| [0033](ADR-0033-taktus-authenticates-to-a-repository-service-as-an-app-of-its-own.md) | Taktus authenticates to a repository service as an app of its own | accepted |
| [0035](ADR-0035-a-time-trigger-fires-once-per-slot.md) | A time trigger fires once per slot, through the elected scheduler | accepted, amended by 0040 |
| [0037](ADR-0037-a-worker-at-capacity-makes-a-step-wait.md) | A worker at capacity makes a step wait | accepted |
| [0038](ADR-0038-an-assignment-is-recorded-before-it-is-handed-over.md) | An assignment is recorded before it is handed over | accepted |
| [0039](ADR-0039-autonomy-is-enforced-at-the-step-boundary.md) | Autonomy is enforced at the step boundary | accepted |
| [0040](ADR-0040-a-channel-account-is-linked-by-the-person-who-holds-it.md) | A channel account is linked by the person who holds it | accepted |
| [0042](ADR-0042-anchors-halt-at-the-step-boundary-and-raise-a-decision-request.md) | Anchors halt at the step boundary and raise a decision request | accepted |
| [0043](ADR-0043-every-block-is-booked-to-an-account-when-it-ends.md) | Every block is booked to an account when it ends | accepted |
| [0044](ADR-0044-the-instance-records-the-conformance-half-it-measured.md) | The instance records the conformance half it measured | accepted |
| [0045](ADR-0045-what-is-needed-from-the-owner-reaches-them-as-one-report-in-three-renderings.md) | What is needed from the owner reaches them as one report in three renderings | accepted |
