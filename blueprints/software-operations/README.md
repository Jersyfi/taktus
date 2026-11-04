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
`exact` (ADR-0192 §1); a match of two readings the rule `match`, `exact` (ADR-0199).

The product's entitlements — what a customer may use — are held in the product, and no open
standard describes them. [`connectors/entitlements.manifest.json`](connectors/entitlements.manifest.json)
is the manifest under which a tenant serves its product's own MCP server with the vendor
connector: the capabilities `entitlements.grants` and the scoped `entitlements.customers`, each
entitlement `{id, customer, product, quantity}`, the customer by the payment provider's
identifier (ADR-0199 §2). A tenant changes `tool` to its own tools' names.

Some rows of UC-03 are parts of another process (NTC-0263): B-3.12, B-4.01, B-4.02, B-4.04
and B-4.06 are declared in B-3.02, and B-4.03 is UC-7.5's count of B-3.02's corrections. A
tenant's plan names `b-3-02` for them.

| Stage | Built | Not built, and what it lacks |
|---|---|---|
| 0 The control loop | B-9.01, the instance's daily report of signals (UC-6.13), counted by `reports_missed`; [B-1.05](processes/B-1.05-new-errors.yaml) new errors filed as an issue, once; [B-7.01](processes/B-7.01-triage.yaml) an arriving issue classified and labelled | B-7.04 keeping pull requests mergeable: no connector lists open pull requests or writes onto an existing branch; the repair itself is the coding worker of `dev-orchestration` P-03 |
| 1 Operation without handwork | [B-1.01](processes/B-1.01-daily-cost.yaml) daily cost; [B-1.04](processes/B-1.04-error-rate.yaml) error rate per function, without the tie to the last deployment; [B-1.06](processes/B-1.06-uptime.yaml) uptime by one HTTP check per path; [B-2.01](processes/B-2.01-model-cost.yaml) model cost, without the credit left; [B-5.02](processes/B-5.02-back-office-health.yaml) back-office health, without its error log; [B-1.02](processes/B-1.02-run-times.yaml) the slowest function by run time, without queries, egress and storage and without the optimisation proposed; [B-1.03](processes/B-1.03-runaway.yaml) the function called most, without throttling it; [B-1.07](processes/B-1.07-database-rules.yaml) two requests of a stranger that must be refused; [B-1.08](processes/B-1.08-backups.yaml) the age of the last backup and of the last restore drill the business's jobs report; [B-1.09](processes/B-1.09-expiry.yaml) a certificate over TLS and a domain over RDAP, whichever expires first; [B-2.03](processes/B-2.03-quotas.yaml) the fullest quota of the outside services, as the metrics store holds it; [B-10.01](processes/B-10.01-deadlines.yaml) a deadline from an iCalendar or CalDAV calendar filed as an issue with its lead time, once; [B-6.01](processes/B-6.01-payment-against-entitlement.yaml) every active payment matched against the product's entitlements; [B-5.06](processes/B-5.06-business-seats.yaml) a business customer's seats paid for against the seats granted, without setting up access (B-3.04's repair) or a renewal (ADR-0196 to ADR-0199) | logs: no open standard serves a query of them (ADR-0111 §7); B-1.09's keys, signing certificates, provisioning profiles and secrets: no open standard publishes their expiry; B-1.10: a secret store's rotation: no generic interface reads a store's metadata, and a store fills files outside Taktus (ADR-0187); B-1.11, B-1.13: `dev-orchestration`'s dependency and removal processes at the tenant's repository; B-1.12: pipeline runners; B-2.02: cost per support case — the spend of a process is read per run (ADR-0148), not grouped by case, and no capability serves it to a process; B-2.03: a quota only the service's own API reports; B-2.04: no provider publishes its retired models in a machine-readable form; B-2.05: the model trials of UC-4.18; B-2.06: no source states a subscription's real use; B-5.01, B-5.05: a task list and a customer system; B-5.03: an account directory — SCIM 2.0 would serve it, and no connector speaks it yet; B-5.04: an audit log of privileged actions; B-5.06: preparing a renewal, for which no capability serves a contract's end |
| 2 Customer contact on its own | [B-3.02](processes/B-3.02-draft-reply.yaml) a reply drafted, held against money by rule, checked by an independent step (B-4.06's check, inside the process), a promise held for a person, labelled, and sent at level 2 after release, under the message frame of UC-7.6, with the response limit B-3.12 as its deadline and B-4.01, B-4.02 and B-4.04 as its evaluation cases, grown from corrected drafts and run every week (NTC-0263); [B-3.04](processes/B-3.04-paid-not-unlocked.yaml) for one customer's case, the payment matched against the entitlement, the cause named and a clear case granted after a person confirmed it; [B-3.06](processes/B-3.06-bug-from-support.yaml) a reported defect filed as an issue, once; the money anchor: [`anchors.json`](anchors.json) halts any act under `payment.*` at every level (ADR-0192 §3) | B-3.03: approving a class of request for sending on its own needs a level per class, and the product holds levels per process and per tool action (UC-7.1), not per a class a step's result names; B-3.01, B-3.05, B-3.07 to B-3.11: a helpdesk, the product's accounts, store reviews, social media, a help centre and a feedback portal; B-3.06: adding a report to an existing issue, and telling the customer when the fix is live; B-4.03 is UC-7.5's count per process and action and needs no bundle; B-4.05 scoring dimensions; B-4.07 the AI-literacy policy, a document of the business |
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
