# Architecture decisions

Every decision with its context, the alternatives rejected and its consequences. An architectural
change arrives as an ADR, not as a pull request without context. Where code and an ADR disagree, the
ADR wins.

| ADR | Title | Status |
|---|---|---|
| [0001](ADR-0001-language.md) | Python as the single server-side language | accepted |
| [0002](ADR-0002-dependencies.md) | Dependencies and the execution environment | accepted |
| [0003](ADR-0003-adapter-obligation.md) | The adapter obligation, enforced in CI | accepted |
| [0004](ADR-0004-method-selection.md) | Method selection: which kind of AI per step | accepted |
| [0005](ADR-0005-step-atomicity.md) | Step atomicity and admission control | accepted |
| [0006](ADR-0006-ledger.md) | The ledger as a content-free hash chain | accepted |
| [0007](ADR-0007-worker-contract.md) | Worker contract over HTTP and SSE | accepted |
| [0008](ADR-0008-decision-request.md) | Decision requests and strategic anchors | accepted, extended by 0022 |
| [0009](ADR-0009-adapter-monorepo.md) | Adapters in the main repository until 1.0.0 | accepted |
| [0010](ADR-0010-accounting.md) | The Takt as a unit of orchestrated work | **proposed** |
| [0011](ADR-0011-process-bundles.md) | Process bundles, optionally mirrored to Git | accepted |
| [0012](ADR-0012-licensing.md) | Licensing and repository visibility | **open — owner decides** |
| [0013](ADR-0013-business-critical.md) | Taktus is business-critical: what follows | accepted |
| [0014](ADR-0014-exactness.md) | Exactness classes | accepted, amended by 0018 |
| [0015](ADR-0015-bottlenecks.md) | Measure waiting, report the marginal value of a change | accepted |
| [0016](ADR-0016-explicit-architecture.md) | Explicit Architecture: cut by component | accepted |
| [0017](ADR-0017-decision-requests-in-the-repository.md) | Decision requests as a repository mechanism | accepted, amended by 0021 |
| [0018](ADR-0018-exactness-applies-to-result-producing-steps.md) | Exactness classes apply to result-producing steps only | accepted |
| [0019](ADR-0019-contract-identity.md) | Contract identity | accepted |
| [0020](ADR-0020-tenants-and-instances.md) | Tenants and instances are different boundaries | accepted |
| [0021](ADR-0021-failure-result-defect-incident.md) | Failure, result defect, incident | accepted |
| [0022](ADR-0022-retroactive-correction-is-anchored.md) | Retroactive correction is anchored by default | accepted |
| [0023](ADR-0023-automatic-emergency-stop-is-rule-based.md) | An automatic emergency stop is rule-based | accepted |
| [0024](ADR-0024-connector-contract.md) | Connector contract on MCP: two directions, a declared effect, an honest repeat | accepted |
| [0025](ADR-0025-where-an-instance-may-run.md) | Where an instance may run | accepted |
