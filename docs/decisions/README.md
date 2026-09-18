# Decision register

The decisions of the Taktus project itself: what the owner was asked, what was answered, and what
was raised as a decision and turned out not to be one. The mechanism is ADR-0017; which questions
reach the owner is stated in [anchors.md](anchors.md); the template is
[TEMPLATE.md](TEMPLATE.md).

The category `DEFECT` is a *documentation defect*: a fault in what the repository says, corrected
and recorded, never asked. A wrong result produced by a run is a *result defect* (ADR-0021) and
never appears in this register.

`open/` holds requests that wait for an answer. A request leaves `open/` in the same commit that
creates its record here. `make gate-decisions` checks both.

| DEC | Title | Category | Outcome |
|---|---|---|---|
| [0001](DEC-0001-contract-identity.md) | Contract identity | NON-BLOCKING | answered: `https://taktus.eu/contracts/<family>/v1/<Concept>.json` (ADR-0019) |
| [0002](DEC-0002-exactness-and-non-producing-steps.md) | Exactness and non-producing steps | DEFECT | corrected: exactness applies to result-producing steps only (ADR-0018) |
| [0003](DEC-0003-where-the-stream-rules-live.md) | Where the stream rules live | NOTE | reclassified: a placement, not a decision |
| [0004](DEC-0004-ci-red-on-empty-targets.md) | CI red on empty targets | BLOCKING | answered: every gate is made meaningful on an empty target |
| [0005](DEC-0005-w12-is-not-a-suite-check.md) | W-12 is not a check the suite can run | DEFECT | corrected: the suite runs W-01 to W-11 and reports the removal test as pending |
| [0006](DEC-0006-gates-assumed-an-installed-environment.md) | The gates assumed an installed environment | DEFECT | corrected: every gate target ensures its environment; `make doctor` checks what the gates invoke |
| [0007](DEC-0007-the-shared-kernel-is-a-checked-binding.md) | The shared kernel is a checked binding, not generated code | DEFECT | corrected: hand-written bindings held to the schemas by `tests/contract` |
| [0008](DEC-0008-the-frame-names-allowed-hosts.md) | The execution frame names allowed hosts, not forbidden ones | DEFECT | corrected: `frame.allowed_hosts` replaces `frame.forbidden`; check W-13 |
| [0009](DEC-0009-credentials-are-parameters.md) | The credential register lists parameters, not deployment names | DEFECT | corrected: every row of `CREDENTIALS.md` is a parameter with purpose, permissions, rotation and its configuration key |
| [0010](DEC-0010-commands-show-the-invocation-that-works.md) | Every command shows the invocation that works | DEFECT | corrected: `uv run` wherever the project environment is involved; the rule is in the conventions |
| [0011](DEC-0011-no-worker-code-in-the-control-plane-image.md) | No worker code in the control plane image | DEFECT | corrected: the reference worker has its own image; `compose.yml` is Taktus and PostgreSQL; `compose.reference-worker.yml` is the development layer; a check fails on worker code in the control plane image |
| [0012](DEC-0012-the-limit-guarantee-holds-per-consumption-kind.md) | The limit guarantee holds per consumption kind | DEFECT | corrected: ADR-0005 names the kinds — tokens, quota, compute per step — for which no limit is breached, and states that a currency limit degrades to an estimate where money is reported per assignment |
| [0013](DEC-0013-a-provisional-operator-identity.md) | A provisional operator identity until the identity component exists | NOTE | recorded: one configured identity per tenant (`TAKTUS_PROVISIONAL_IDENTITY`), marked provisional everywhere it appears; the identity component (`0.2.0`) replaces it and removes the variable |
