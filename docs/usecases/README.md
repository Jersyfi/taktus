# Use cases

Two levels.

**Blueprint-level cases** describe one whole business function run by Taktus: which processes,
at which autonomy, with which anchors. One file per blueprint.

| Case | Blueprint | File | Version |
|---|---|---|---|
| UC-01 | product development, unattended | [AF-01-dev-orchestration.md](AF-01-dev-orchestration.md) | `0.4.0` |
| UC-02 | systems operation, unattended | [AF-02-it-operations.md](AF-02-it-operations.md) | `0.7.0` |

**Function-level cases** describe one thing Taktus does, for every blueprint, as a
specification the implementation is held to. They are numbered `UC-<area>.<case>`; the areas
are 4 — execution and results, 6 — reporting and delivery, 7 — governance. Cases that the
architecture documents already describe are listed with their place; the rest have a file.

| Case | Title | Where | Version |
|---|---|---|---|
| UC-4.5 | A step fails: halt or escalate at the boundary | [control-plane.md §5.2](../architecture/control-plane.md) | `0.1.0` |
| UC-4.6 | Self-healing within the frame | [control-plane.md §5.2](../architecture/control-plane.md) | `0.2.0` |
| UC-4.10 | Deviation detection | [UC-4-result-defects.md](UC-4-result-defects.md) | `0.5.0` |
| UC-4.11 | Error window and impact analysis | [UC-4-result-defects.md](UC-4-result-defects.md) | `0.5.0` |
| UC-4.12 | Remediation plan | [UC-4-result-defects.md](UC-4-result-defects.md) | `0.5.0` |
| UC-4.13 | Working out how a step becomes exact | [UC-4-exactness-statement.md](UC-4-exactness-statement.md) | `0.5.0` |
| UC-6.8 | Incident and incident report | [UC-4-result-defects.md](UC-4-result-defects.md) | `0.5.0` |
| UC-6.9 | The exactness statement | [UC-4-exactness-statement.md](UC-4-exactness-statement.md) | `0.5.0` |
| UC-7.2 | Emergency stop | [UC-4-result-defects.md](UC-4-result-defects.md) | by a person `0.2.0`, automatic `0.5.0` |

A function-level case has five parts: the situation, what Taktus does, what it needs, what it
never does, and how it is proven. A case is written before its version and is not implementation:
the implementation arrives in the version named and is held to the case by tests.
