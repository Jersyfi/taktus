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

The product provides each stage's processes; the business introduces them on its own instance
and opens each stage itself (DEC-0201). Nothing here says that a stage ran at the tenant.

Every process is a bundle under [`processes/`](processes/), named `b-<area>-<number>`, the
identifier [`stages.yaml`](stages.yaml) names it by (ADR-0191 §4). A process that only reads and
judges starts at level 1, one that acts at level 2 (UC-03 §4). Each is registered as shipped and
run against fakes of the systems behind its capabilities in
`tests/composition/test_software_operations.py`; the cost watchers in
`tests/composition/test_cost_watcher.py`. A selection over a reading is the rule `filter`,
`exact` (ADR-0192 §1).

| Stage | Built | Not built, and what it lacks |
|---|---|---|
| 0 The control loop | B-9.01, the instance's daily report of signals (UC-6.13), counted by `reports_missed`; [B-1.05](processes/B-1.05-new-errors.yaml) new errors filed as an issue, once; [B-7.01](processes/B-7.01-triage.yaml) an arriving issue classified and labelled | B-7.04 keeping pull requests mergeable: no connector lists open pull requests or writes onto an existing branch; the repair itself is the coding worker of `dev-orchestration` P-03 |
| 1 Operation without handwork | [B-1.01](processes/B-1.01-daily-cost.yaml) daily cost; [B-1.04](processes/B-1.04-error-rate.yaml) error rate per function, without the tie to the last deployment; [B-1.06](processes/B-1.06-uptime.yaml) uptime by one HTTP check per path; [B-2.01](processes/B-2.01-model-cost.yaml) model cost, without the credit left; [B-5.02](processes/B-5.02-back-office-health.yaml) back-office health, without its error log | B-1.02, B-1.03: logs and function run times; B-1.07: database rules; B-1.08: a backup and restore of the business's own systems; B-1.09: expiry dates of domains, certificates and keys; B-1.10: a secret store's rotation; B-1.11, B-1.13: `dev-orchestration`'s dependency and removal processes at the tenant's repository; B-1.12: pipeline runners; B-2.02: cost per support case; B-2.03: quotas of outside services; B-2.04 to B-2.06: model release notes, evaluations and a subscription inventory; B-5.01, B-5.05: a task list and a customer system; B-5.03: an account directory; B-5.04: an audit log of privileged actions; B-5.06: seats against billing; B-6.01: the product's entitlements, and a rule that matches two lists; B-10.01: a deadline calendar |
| 2 Customer contact on its own | [B-3.02](processes/B-3.02-draft-reply.yaml) a reply drafted, held against money by rule, checked by an independent step (B-4.06's check, inside the process), a promise held for a person, labelled, and sent at level 2 after release, under the message frame of UC-7.6; the money anchor: [`anchors.json`](anchors.json) halts any act under `payment.*` at every level (ADR-0192 §3) | B-3.03: approving a class for sending on its own is a raise of B-3.02's action by a person on its history (UC-7.1), and the classes themselves need a classifying step; B-3.01, B-3.05 to B-3.12: a helpdesk, the product's accounts and entitlements, store reviews, social media, a help centre and a feedback portal; B-3.04: the product's entitlements; §4.4: B-4.01, B-4.02 and B-4.04 are the evaluations of UC-4.18 on B-3.02's own cases, B-4.03 the correction rates of UC-7.5, B-4.05 scoring dimensions and B-4.07 the AI-literacy policy |
| 3 Release without people | — | §4.8: no connector serves app stores, staged rollout or a deployment target with rollback |
| 4 Development end to end | B-7.01 above; `dev-orchestration` P-02 and P-03 serve B-7.02 and B-7.03 once instantiated with the tenant's repository | B-7.12: no connector merges a pull request, and the paths a change touches are not known at the step's boundary for a protected-path anchor; B-7.04, B-7.05, B-7.06 to B-7.11 |
| 5 The business runs dark | — | §4.6, §4.9, §4.10 beyond the processes above |

[`stages.yaml`](stages.yaml) proposes UC-03's six stages, each with the processes it adds, the
level each may reach once the stage is open, and the condition under which it holds (ADR-0137,
NTC-0232). A stage opens, and holds, only while every process it adds has an active version, and
stage 0 counts the days without the daily report (ADR-0191). A tenant declares its plan from
them with `taktusctl stage declare --blueprint blueprints/software-operations/stages.yaml
--responsible <role>`, and may make every condition stricter, never looser. Its responsible role
reads the stages and opens them at `GET /stages` and `POST /stages/{stage}/open`, or by
`taktusctl stage show` and `open`.

[`anchors.json`](anchors.json) proposes the anchors of UC-03 §6 that a capability names:
moving money, legal acts and corrections (ADR-0192 §3). A tenant takes it with `taktusctl
anchors set blueprints/software-operations/anchors.json`, with its own deciding role in place of
`owner`.

The business installs its instance with the administration guide
(`docs/guides/administration/first-install.md`), which registers each bundle of this blueprint.
The issues of the stages are #400 (stage 0), #437 (stage 1), #401 (stage 2), #438 (stage 3),
#439 (stage 4) and #440 (stage 5).
