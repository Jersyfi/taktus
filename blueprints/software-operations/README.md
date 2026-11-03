# Blueprint `software-operations`

The operation of a small software business, run by Taktus and introduced into it in six stages.
Its requirement is use case UC-03, [`docs/usecases/AF-03-software-operations.md`](../../docs/usecases/AF-03-software-operations.md):
96 processes in eleven areas, their target levels, what stays with a person, and the stages.

It is the blueprint of Taktus's second tenant (DEC-0199). The blueprint is product: its
processes name capabilities only. The tenant's instantiation — the systems behind each
capability, thresholds, anchors, roles — is the tenant's configuration on its own instance and
never enters this repository (ADR-0092, NEED-0027 §5).

Development at the tenant runs on [`dev-orchestration`](../dev-orchestration/README.md).

## State

A description, and the first bundles: [`processes/B-1.01-daily-cost.yaml`](processes/B-1.01-daily-cost.yaml),
the cost watcher of stage 1, and [`processes/B-2.01-model-cost.yaml`](processes/B-2.01-model-cost.yaml),
the same watcher over a model provider's spend, through `models.costs`; the credit left, the
other half of B-2.01, is not read yet. Each measures the day's cost with
the statistic `deviation` (ADR-0151), and leaves the judgement to the tenant's corridor on its
`ratio`, which raises an incident when the day left it (ADR-0109). [`stages.yaml`](stages.yaml) proposes UC-03's six
stages, each with the processes it adds, the level each may reach once the stage is open, and
the condition under which it holds (ADR-0137, NTC-0232). A tenant declares its plan from them
with `taktusctl stage declare --blueprint blueprints/software-operations/stages.yaml
--responsible <role>`, and may make every condition stricter, never looser. The business installs its instance with the
administration guide (`docs/guides/administration/first-install.md`), which registers each
bundle of this blueprint once there is one. Stage 0 is #400 (`0.4.0`); stage 1 is #437, stage 2
#401, stage 3 #438, stage 4 #439, stage 5 #440.
