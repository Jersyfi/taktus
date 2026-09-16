# Decision register

The decisions of the Taktus project itself: what the owner was asked, what was answered, and what
was raised as a decision and turned out not to be one. The mechanism is ADR-0017; which questions
reach the owner is stated in [anchors.md](anchors.md); the template is
[TEMPLATE.md](TEMPLATE.md).

`open/` holds requests that wait for an answer. A request leaves `open/` in the same commit that
creates its record here. `make gate-decisions` checks both.

| DEC | Title | Category | Outcome |
|---|---|---|---|
| [0001](DEC-0001-contract-identity.md) | Contract identity | NON-BLOCKING | answered: `https://taktus.eu/contracts/<family>/v1/<Concept>.json` (ADR-0019) |
| [0002](DEC-0002-exactness-and-non-producing-steps.md) | Exactness and non-producing steps | DEFECT | corrected: exactness applies to result-producing steps only (ADR-0018) |
| [0003](DEC-0003-where-the-stream-rules-live.md) | Where the stream rules live | NOTE | reclassified: a placement, not a decision |
| [0004](DEC-0004-ci-red-on-empty-targets.md) | CI red on empty targets | BLOCKING | answered: every gate is made meaningful on an empty target |
