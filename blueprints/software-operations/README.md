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
`tests/composition/test_cost_watcher.py`; the repository and release processes in
`tests/composition/test_software_operations_repository.py`; the logs, secrets, signing credentials, repository infrastructure and model catalogue of stage 1 in `tests/composition/test_software_operations_ops.py`. A selection over a reading is the rule `filter`,
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
| 0 The control loop | B-9.01, the instance's daily report of signals (UC-6.13), counted by `reports_missed`; [B-1.05](processes/B-1.05-new-errors.yaml) new errors filed as an issue, once; [B-7.01](processes/B-7.01-triage.yaml) an arriving issue classified and labelled; [B-7.04](processes/B-7.04-mergeable.yaml) one open pull request per run brought up to date with its base, or its red pipeline repaired by the coding worker on its own branch, a repair that changes a protected path held for a person's decision (ADR-0193, ADR-0194) | B-7.04's schedule: the tenant's version adds it with its own clone; a merge conflict goes to a person, not resolved by the worker |
| 1 Operation without handwork | [B-1.01](processes/B-1.01-daily-cost.yaml) daily cost; [B-1.04](processes/B-1.04-error-rate.yaml) error rate per function, and the errors logged since the last deployment's rollout (ADR-0201, ADR-0202); [B-1.06](processes/B-1.06-uptime.yaml) uptime by one HTTP check per path; [B-2.01](processes/B-2.01-model-cost.yaml) model cost, without the credit left; [B-5.02](processes/B-5.02-back-office-health.yaml) back-office health, with its error log counted; [B-1.02](processes/B-1.02-run-times.yaml) the slowest function by run time, without queries, egress and storage and without the optimisation proposed; [B-1.03](processes/B-1.03-runaway.yaml) the function called most, without throttling it; [B-1.07](processes/B-1.07-database-rules.yaml) two requests of a stranger that must be refused; [B-1.08](processes/B-1.08-backups.yaml) the age of the last backup and of the last restore drill the business's jobs report; [B-1.09](processes/B-1.09-expiry.yaml) a certificate over TLS and a domain over RDAP, whichever expires first, and the signing certificate or provisioning profile that expires first (ADR-0203); [B-1.10](processes/B-1.10-rotation-watch.yaml) the secret whose value is oldest past the tenant's age filed with its rotation prepared, no value read and the rotation left to a person (ADR-0203); [B-1.11](processes/B-1.11-advisories.yaml) an open dependency alert a patched version fixes filed as the implementation process's goal, once (ADR-0201); [B-1.13](processes/B-1.13-superseded-code.yaml) a deprecated endpoint's removal filed with its remaining calls from the logs, as the implementation process's goal (ADR-0202); [B-2.04](processes/B-2.04-retired-models.yaml) the models in use the provider lists as deprecated, retired or scheduled, or no longer lists, filed as one switch, once (ADR-0204); [B-2.03](processes/B-2.03-quotas.yaml) the fullest quota of the outside services, as the metrics store holds it, and the fullest of the repository service's own rate limits (ADR-0201); [B-10.01](processes/B-10.01-deadlines.yaml) a deadline from an iCalendar or CalDAV calendar filed as an issue with its lead time, once; [B-6.01](processes/B-6.01-payment-against-entitlement.yaml) every active payment matched against the product's entitlements; [B-5.06](processes/B-5.06-business-seats.yaml) a business customer's seats paid for against the seats granted, without setting up access (B-3.04's repair) or a renewal (ADR-0196 to ADR-0199); [B-1.12](processes/B-1.12-pipeline-runs.yaml) pipeline runs queued or in progress too long, counted for the tenant's corridor, the run in progress longest cancelled and rerun once a person confirmed it, and the runners offline counted (ADR-0201); B-1.01's costs over a second cloud's billing export (`gcp`, ADR-0204) | B-1.09's keys: no store the business names publishes a key's expiry; B-1.10's consumers of a secret: no store states who reads one, and triggering a rotation stays with a person (ADR-0203); B-1.11, B-1.13, B-2.04: the pull request itself is P-03's on the filed issue, and a major update stays with a person; B-1.12's runner removal, which changes the pool, and its weekly cost: the service bills the account, and no capability reads it (ADR-0201); a cloud's costs through its Budget API: it answers budgets, not spend (ADR-0204); B-2.02: cost per support case — the spend of a process is read per run (ADR-0148), not grouped by case, and no capability serves it to a process; B-2.03: a quota only another service's own API reports; B-2.04: finding the model identifiers in the code — no capability searches it, and the tenant's version names them; B-2.05: the model trials of UC-4.18; B-2.06: no source states a subscription's real use; B-5.01, B-5.05: a task list and a customer system; B-5.03: an account directory — SCIM 2.0 would serve it, and no connector speaks it yet; B-5.04: an audit log of privileged actions; B-5.06: preparing a renewal, for which no capability serves a contract's end |
| 2 Customer contact on its own | [B-3.02](processes/B-3.02-draft-reply.yaml) a reply drafted, held against money by rule, checked by an independent step (B-4.06's check, inside the process), a promise held for a person, labelled, and sent at level 2 after release, under the message frame of UC-7.6, with the response limit B-3.12 as its deadline and B-4.01, B-4.02 and B-4.04 as its evaluation cases, grown from corrected drafts and run every week (NTC-0263); [B-3.04](processes/B-3.04-paid-not-unlocked.yaml) for one customer's case, the payment matched against the entitlement, the cause named and a clear case granted after a person confirmed it; [B-3.06](processes/B-3.06-bug-from-support.yaml) a reported defect filed as an issue, once; the money anchor: [`anchors.json`](anchors.json) halts any act under `payment.*` at every level (ADR-0192 §3) | B-3.03: approving a class of request for sending on its own needs a level per class, and the product holds levels per process and per tool action (UC-7.1), not per a class a step's result names; B-3.01, B-3.05, B-3.07 to B-3.11: a helpdesk, the product's accounts, store reviews, social media, a help centre and a feedback portal; B-3.06: adding a report to an existing issue, and telling the customer when the fix is live; B-4.03 is UC-7.5's count per process and action and needs no bundle; B-4.05 scoring dimensions; B-4.07 the AI-literacy policy, a document of the business |
| 3 Release without people | [B-8.04](processes/B-8.04-staged-rollout.yaml) a canary raised in three stages while its error rate holds, and scaled to zero by rule on a rise; [B-8.05](processes/B-8.05-web-deployment.yaml) a release rolled out, a smoke test run, and the rollback put to a person when it fails; [B-8.06](processes/B-8.06-backend-deployment.yaml) a release rolled out, its error rate read after thirty minutes, and the rollback put to a person on a rise; [B-8.07](processes/B-8.07-release-hygiene.yaml) a release pull request open past three days reminded with its blockers; a deployment through `deployment.workloads` (ADR-0195) | B-8.01 and B-8.08: drafting a changelog, store texts and a newsletter from the merged changes; B-8.02, B-8.03 and a store's staged rollout: each store's own interface; a deployment that is not a workload of a cluster's API |
| 4 Development end to end | B-7.01 and B-7.04 above; `dev-orchestration` P-02 and P-03 serve B-7.02 and B-7.03 once instantiated with the tenant's repository; [B-7.05](processes/B-7.05-review.yaml) every pull request reviewed by a model that is not shown its author, with the repository's own count of what it adds and removes; [B-7.10](processes/B-7.10-abandoned-work.yaml) pull requests idle two weeks, started issues still a week and branches without an open pull request, counted for the tenant's corridor (ADR-0201); [B-7.12](processes/B-7.12-merge-by-policy.yaml) a green pull request of documentation or a patch update merged at the head it read, under the policy its version is, a protected path held for a person's decision (ADR-0194) | B-7.06, B-7.07, B-7.11: a coding task without an issue — a refactoring, a friction found, documentation checked against the code — is P-03's worker given another goal, and no bundle states those goals yet; B-7.07, B-7.08 and B-7.09: a worker with a browser |
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
