# UC-03 — Operating a software business, introduced in stages

Blueprint `software-operations`. Reference case: a small software business with a web and a
mobile app, a cloud backend, subscriptions, private and business customers, and agents in
support and development. Taktus runs its operation, process by process. In normal operation
the business needs no staff for it. People set the goals, the limits and the budgets, carry the
liability and sign.

This is the second tenant and the case Taktus proves itself on (DEC-0199). `1.0.0` is complete
only when it holds (§9).

---

## 1. The task in one sentence

Taktus watches, prepares and carries out the recurring work of a software business across
eleven areas. It is introduced into the running operation in six stages, each opened only when
the previous one measurably holds. Every process rises in autonomy only on counted evidence and
falls back by rule.

---

## 2. Origin and boundary

This case is derived from one business's catalogue of 96 use cases, received on 2026-10-14. The
catalogue stays outside this repository (NEED-0027 §5). What is written here is what Taktus
must do, in its own words. It names nothing of the business: no system, no amount, no person.

**The blueprint is product.** Its processes are generic and name capabilities only, never
products (CLAUDE.md §6). Another software business can instantiate it.

**The instantiation is the tenant's.** Which system serves each capability, the thresholds,
the anchors, the roles and the people stay in the tenant's own configuration, on its instance
(ADR-0092). The systems themselves are NEED-0028.

**The business hosts and operates Taktus itself** (DEC-0201). It installs and upgrades its
instance from the documentation, and a person of the business opens each stage. The project
never acts on its instance and never receives its data. What the business meets that the
product lacks reaches this repository as a product finding, once its operator enables it
(UC-6.12, #446). Every connector it needs is built in this repository, as product.

**Taktus keeps no second truth** (non-goals). Code work stays in the business's repository
service. Customer cases stay in its helpdesk or its customer system. Bookkeeping stays in its
accounting system. Taktus holds runs, incidents and decision requests, and links to the place
where each case is worked (UC-5.3, UC-6.8).

---

## 3. Autonomy

The catalogue names four stages. They are Taktus's four levels (UC-7.1).

| Catalogue | Means | Taktus level |
|---|---|---|
| A0 observes | measures and reports, changes nothing | 1 — observe and propose |
| A1 prepares | writes a draft, a diagnosis or a pull request; a person releases it | 2 — execute after approval |
| A2 acts and reports | acts, then reports; a person can undo it | 3 — autonomous under supervision |
| A3 acts silently | acts; reports only a deviation | 4 — human out of the loop |

**Rising.** A process rises one level only on evidence: a number of runs and weeks with a
correction rate below a limit. The tenant sets the numbers. A person approves every raise
(UC-7.1, UC-7.5).

**Falling.** A process falls back by rule. It falls on any breach of what stays with a person
(§6), or when corrections accumulate beyond a limit (UC-7.5).

**Autonomy belongs to the action as well as the process** (UC-02 §1). One process may send an
approved class of reply at level 3 and hold every other class at level 2.

---

## 4. Processes

Ninety-six processes in eleven areas. *Level* is the target level, not the starting level.
Every process starts at level 1 or 2 when its stage opens (§5). *Stays with a person* holds at
every level. *Rests on* names the use cases that make the process possible.

A figure marked `exact` is produced by a `rule` or `statistics` step with a check (UC-4.10,
ADR-0082). No language model produces it (CLAUDE.md §4).

### 4.1 Infrastructure and cloud cost

| ID | Process | Trigger | Level | Stays with a person | Rests on |
|---|---|---|---|---|---|
| B-1.01 | Daily cost: the day against its median, the service behind a jump named, an incident raised | daily, from the billing export | 3 | raising a budget, throttling a service | UC-6.13, UC-6.8; cost `exact` |
| B-1.02 | Cost drivers: expensive queries, function run times, egress and storage analysed; optimisations proposed as an issue or a pull request | monthly, or on a budget alert | 3 | the priority | UC-01 P-03 |
| B-1.03 | Runaway guard: endless loops found (triggers reacting to their own writes, retry storms), the function named, throttled in an emergency | instance count or call rate above a threshold | 3 | changing a limit for good | UC-6.13, UC-7.1 action class |
| B-1.04 | Error rate of server functions: errors grouped by function and release, tied to the last deployment, a fix pull request opened | error rate per function above its baseline | 4 | releasing a hotfix | UC-6.13, UC-4.14, UC-01 P-03 |
| B-1.05 | New errors in error tracking: classified, reproduced, a focused fix pull request opened | a new error with many users, or in the payment or sign-in path | 4 | the merge | UC-4.14, UC-01 P-05, P-03 |
| B-1.06 | Uptime and synthetic checks: web app, sign-in, API, webhooks and website checked with a real flow; an incident after two failures | every five minutes | 3 | telling customers about a long outage | UC-4.16, UC-6.8 |
| B-1.07 | Database rules and indexes: rules tested against attack patterns (reading others' data, counting up identifiers), an index deployment checked | a change to security rules or indexes | 2 | the merge of the rules | UC-01 P-04 |
| B-1.08 | Backup and restore drill: whether the backup ran, daily; a monthly restore into a test environment with samples compared | daily and monthly | 3 | a restore in an emergency | UC-4.16, UC-02 O-03 |
| B-1.09 | Things that expire: domains, certificates, keys, signing certificates, provisioning profiles, secrets listed and renewed where renewal is free | 30 days before expiry | 3 | a renewal that costs money | UC-4.17 |
| B-1.10 | Rotating a secret: the secret identified, the rotation prepared, every consumer listed | a schedule, or a secret found in code | 2 | triggering the rotation | UC-7.3 |
| B-1.11 | Dependencies and advisories: updates applied, broken builds repaired, patch level taken after a green pipeline | a new update or advisory | 4 | major updates | UC-01 P-10, UC-7.1 action class |
| B-1.12 | Pipeline infrastructure: lost jobs restarted, runners cleaned up, the pipeline's weekly cost reported | a lost job, a hung runner, a rise in cost | 4 | pool sizes, runner types | UC-6.13 |
| B-1.13 | Superseded code: a removal pull request opened, the remaining calls shown from the logs | the expiry date of a deprecated endpoint | 3 | the merge | UC-4.17 |

### 4.2 The budget for models and outside services

| ID | Process | Trigger | Level | Stays with a person | Rests on |
|---|---|---|---|---|---|
| B-2.01 | Model credit: balance and use per provider read, the days left computed, a warning before it runs out | daily, and at a threshold | 2 | topping up | UC-6.13; days left `exact` |
| B-2.02 | Cost per process and per case: model cost attributed to the process, the support case or the pull request; a process paused at its budget | every run | 3 | changing a budget | UC-8.5 |
| B-2.03 | Quotas of outside services: mail sending, payments, data services, the repository service's rate limits against their quota | daily | 3 | changing a plan | UC-6.13 |
| B-2.04 | Retired models: retired model identifiers found in the code, old against new evaluated, a pull request with the switch | weekly, from the providers' release notes | 3 | releasing the switch | UC-4.18, UC-8.2 |
| B-2.05 | Comparing models: the evaluation set run against old and new; quality, cost and latency side by side | a new model is available | 2 | the switch | UC-4.18 |
| B-2.06 | Subscription inventory: every subscription with its cost and its real use, cancellation or building it in-house proposed | quarterly | 2 | cancelling | UC-6.2 |

### 4.3 Customer service

| ID | Process | Trigger | Level | Stays with a person | Rests on |
|---|---|---|---|---|---|
| B-3.01 | Sorting the inbox: spam, bounces, cold sales, tests and applications recognised and closed without a reply | every incoming message | 4 | — | UC-4.14; the first candidate to mature from a language model to a trained model (#218) |
| B-3.02 | Drafting a reply: the request classified, the sender's account, subscription and data read through tools, a reply drafted and checked by rule | a real request | 3 | releasing it, until its class is raised | UC-7.7, UC-7.6, UC-7.5 |
| B-3.03 | Sending automatically: sent with an AI label, with a sending delay and quiet hours; stopped once a person answers in the case | an approved class, every check green | 3 | which classes are approved | UC-7.6 |
| B-3.04 | "Paid but not unlocked": the payment at the payment provider matched against the entitlement in the account, the cause named, clear cases repaired | a request about payment or access | 3 | a refund | match `exact`; UC-7.1 action class |
| B-3.05 | Cancellation and subscription questions: the subscription's state and history shown, the self-service way explained | a request about cancelling or a charge | 2 | goodwill, a refund | UC-7.7 |
| B-3.06 | A bug from support: an issue with reproduction, device, version and a link back, or added to an existing one; the customer told when the fix is live | a defect report | 4 | — | UC-5.3, UC-7.6 |
| B-3.07 | A feature wish: taken into the feedback portal with the customer's consent, or a vote counted | a wish in support | 3 | — | UC-5.3 |
| B-3.08 | Data protection requests: the request recognised, the identity checked, the export or erasure prepared, the deadline watched | access, erasure, rectification | 2 | carrying it out and confirming it | UC-4.17, UC-7.7 |
| B-3.09 | Store reviews: a reply drafted, tied to a known bug, patterns across releases found | a new review, especially of one or two stars | 3 | releasing the reply | UC-7.6 |
| B-3.10 | Mentions on social media and in forums: found and sorted into support case, praise and criticism | continuous | 2 | answering in public | UC-7.6 |
| B-3.11 | Gaps in the help centre: an article drafted from answered cases, without copying old answers as a template | a recurring question without an article | 2 | publishing | UC-7.7 |
| B-3.12 | Response limit: a case escalated and attached to the responsible role | a case unanswered longer than its limit | 3 | — | UC-4.17 |

### 4.4 The quality of the support agent

| ID | Process | Trigger | Level | Stays with a person | Rests on |
|---|---|---|---|---|---|
| B-4.01 | Evaluation on change: the evaluation set run against the real model, a regression blocked | a change of prompt, tools or model | 4 | — | UC-4.18 |
| B-4.02 | Drift run: the same run without a change, because model and knowledge change under the same name | weekly | 4 | — | UC-4.18 |
| B-4.03 | Correction rate: corrections counted over 7 and 28 days, readiness for a raise and a fall reported | every change a person makes to a draft | 1 | raising or lowering | UC-7.5 |
| B-4.04 | Growing the evaluation set: a corrected case proposed as a new evaluation case with its target answer | a corrected draft | 2 | confirming the target answer | UC-4.18 |
| B-4.05 | Scoring in dimensions: every draft scored on fixed dimensions with yes-or-no gates; whether it is sent is decided by a rule, not by a model | every draft | 3 | setting the thresholds | UC-7.6 |
| B-4.06 | Independent check: a second step that may only send or reject checks the draft against the raw tool results | before every send | 4 | — | UC-7.6 |
| B-4.07 | Duties under the AI Act: the label checked, the policy on AI literacy kept current | the first automatic send, a change of rules | 2 | the legal responsibility | UC-7.6, UC-15.5 |

### 4.5 Back office and internal tools

| ID | Process | Trigger | Level | Stays with a person | Rests on |
|---|---|---|---|---|---|
| B-5.01 | Overdue tasks: open tasks and flagged messages listed by age, the responsible person reminded, escalated after a deadline | daily | 3 | doing them | UC-4.17; reminders go to the person, counts only by role |
| B-5.02 | Back-office health: sign-in, API, notifications and background jobs of the back office checked, its error log read | continuous | 3 | — | UC-4.16, UC-6.13 |
| B-5.03 | Access review: internal accounts, roles, bot and service access listed; inactive and over-privileged accounts marked | monthly | 2 | revoking access | UC-7.3 |
| B-5.04 | Auditing privileged actions: unusual patterns reported — mass changes, escalation of rights, an action outside an organisation-wide time window | every privileged action | 1 | the investigation | principle 14: a rule on the action, never a learned profile of a person (DEC-0199) |
| B-5.05 | Customer system upkeep: contacts and touchpoints assigned, follow-ups proposed, duplicates merged | a mail, an appointment, a lead | 3 | sending an offer | UC-5.3; Taktus is not the customer system |
| B-5.06 | Business customers: seats checked against billing, access set up, a renewal prepared | a new customer, a change of seats, a contract's end | 3 | the contract, the price | seats `exact` |

### 4.6 Revenue and billing

| ID | Process | Trigger | Level | Stays with a person | Rests on |
|---|---|---|---|---|---|
| B-6.01 | Payment against entitlement: every active payment at every payment provider matched against the product's entitlements; every mismatch an incident | daily | 3 | a refund | match `exact`; UC-6.8 |
| B-6.02 | Lost webhooks: missing events found and replayed so that a repeat changes nothing | failed or missing events | 4 | — | ADR-0024 |
| B-6.03 | Recurring revenue and churn: revenue, new subscriptions, cancellations and failed payments against their 7-day median; a push on red | daily | 1 | the reaction | figures `exact`; UC-6.13 |
| B-6.04 | Failed payments: the customer reminded in stages, a way to update the payment method offered | a declined card, a returned debit | 3 | blocking access | UC-7.6 |
| B-6.05 | Dunning business customers: reminded in stages; Taktus never blocks | an overdue invoice | 2 | blocking, collection | UC-7.6, UC-4.17 |
| B-6.06 | Invoices and receipts: outgoing and incoming invoices collected, matched, exported for the bookkeeping | monthly | 3 | tax, release | #402; Taktus keeps no books |
| B-6.07 | Price experiments: variants evaluated, significance checked, a recommendation written | planned | 2 | changing a price | significance by `statistics` |

### 4.7 Development

Development runs on the `dev-orchestration` blueprint (UC-01), at this tenant's repository.

| ID | Process | Trigger | Level | Stays with a person | Rests on |
|---|---|---|---|---|---|
| B-7.01 | Triage: what arrives from support, feedback and error tracking turned into issues, de-duplicated, classified | weekly, and on arrival | 3 | the top priority | UC-01 P-05 |
| B-7.02 | Refining an issue: acceptance criteria, reproduction and affected places added until an agent can carry it out | a vague issue | 3 | confirming the specification | UC-01 P-02 |
| B-7.03 | Implementing an issue: branch, change, tests, pull request | a schedule, the ready issue with the highest priority | 4 | the merge | UC-01 P-03 |
| B-7.04 | Keeping pull requests mergeable: rebased, the pipeline repaired, review comments worked in | several times a day | 4 | the merge | UC-01 P-03 |
| B-7.05 | Review: correctness, security and the balance of what was added and removed | every pull request | 4 | — | UC-01 P-04 |
| B-7.06 | Technical debt: one focused refactoring or removal of dead code per run | planned | 4 | the merge | UC-01 P-03 |
| B-7.07 | Friction in the product: flows clicked through, friction found, one improvement as a pull request | planned | 3 | the merge | UC-01 P-03 |
| B-7.08 | Daily acceptance: the app built, end-to-end flows and screenshots run and compared with the day before, regressions as issues | after every merge to the main branch | 3 | — | UC-01 P-07; a worker with a browser |
| B-7.09 | Penetration test: as a test user, read others' data, count up identifiers, call admin routes — from a fresh context without the source, as an outside attacker | after a larger feature | 3 | releasing the fix | UC-7.3 |
| B-7.10 | Abandoned work: branches without a pull request, pull requests lying still and started issues without movement reported | daily | 3 | cleaning up | UC-01 P-10 |
| B-7.11 | Documentation kept current: documentation and agent instructions checked against the code, a pull request opened | after a merge | 3 | the merge | UC-01 P-06 |
| B-7.12 | A merge by a reviewing step: a second step that knows nothing of the author checks against a written policy and merges narrow classes (patch updates, documentation) | a green pull request that meets the policy | 3 | setting the policy | UC-01 P-04, UC-7.1 action class |

### 4.8 Release and deployment

| ID | Process | Trigger | Level | Stays with a person | Rests on |
|---|---|---|---|---|---|
| B-8.01 | Preparing a release: changes collected; test plan, changelog, store texts and newsletter drafted | a release branch or release pull request | 3 | releasing the texts | UC-01 P-09 |
| B-8.02 | Distributing a beta: sent to test channels, testers' feedback collected, issues raised | a finished build | 4 | — | UC-4.14 |
| B-8.03 | Store submission: metadata and screenshots prepared, the review followed, a rejection reported at once | an approved release | 2 | submitting | UC-7.6 |
| B-8.04 | Staged rollout: the rollout raised by crash rate and error corridor, halted by itself on a rise | after publishing | 3 | resuming after a halt | UC-6.13, UC-7.2 |
| B-8.05 | Web deployment: deployed, a smoke test run, a rollback triggered on failure | a published release | 3 | confirming the rollback | UC-6.13, UC-4.6 |
| B-8.06 | Backend deployment: deployed, the error rate watched for 30 minutes, a rollback proposed | a merge with a backend change | 3 | the rollback | UC-6.13 |
| B-8.07 | Release hygiene: a reminder, the blockers named | a release pull request open past its limit | 3 | — | UC-4.17 |
| B-8.08 | Changelog and website: a changelog entry and a blog draft; links and search terms checked | a release | 2 | publishing | UC-7.6 |

### 4.9 Product, data and growth

| ID | Process | Trigger | Level | Stays with a person | Rests on |
|---|---|---|---|---|---|
| B-9.01 | The daily report: every signal measured against its corridor, only deviations reported, every line with a link; an intervention carried out from the reply | every morning | 1 | reading it, intervening | UC-6.13, UC-1.5 |
| B-9.02 | Questions about figures: read-only analysis on a copy without personal fields (retention, activation, cohorts); never any outside contact | a question from the team | 3 | — | UC-7.7 |
| B-9.03 | Weekly trends: trends that broke no corridor summarised | weekly | 3 | — | UC-6.2 |
| B-9.04 | Clustering feature wishes: wishes grouped, votes counted, clusters without a place on the roadmap shown | weekly | 3 | the order of the roadmap | UC-5.3 |
| B-9.05 | Data quality: gaps, duplicates and obvious errors in master data found and corrected by a script, never from a model's answer | continuous | 3 | — | correction by `rule` |
| B-9.06 | Onboarding drop-offs: where people leave the funnel, hypotheses and experiments proposed | weekly | 2 | starting an experiment | UC-7.7 |
| B-9.07 | Newsletter: a draft, a segment proposed | a release, monthly | 2 | sending to the list | UC-7.6 |
| B-9.08 | Store optimisation: keyword rankings, competitors on the business's own brand terms, screenshot tests | monthly | 2 | releasing a change | UC-7.6 |
| B-9.09 | Business leads: the company researched, an offer drafted | an enquiry or research | 2 | the price, sending | UC-7.6 |
| B-9.10 | Watching competitors: their releases, prices and reviews summarised | monthly | 3 | — | UC-6.2 |

### 4.10 Administration and compliance

| ID | Process | Trigger | Level | Stays with a person | Rests on |
|---|---|---|---|---|---|
| B-10.01 | Deadline calendar: tax, contract, notice and renewal deadlines as tasks with lead time | continuous | 3 | acting | UC-4.17 |
| B-10.02 | Processing agreements: a new outside service found in a pull request; agreement, data region and retention checked; the record of processing kept | a new outside service in the code | 2 | concluding the agreement | UC-15.5 |
| B-10.03 | Incoming invoices: an invoice matched to a subscription or project and checked against what was expected | a mail with an invoice | 3 | paying | #402; amount `exact` |
| B-10.04 | Licences of dependencies: the licence checked, conflicts reported, the attribution file kept | a new dependency | 4 | an exception | UC-01 P-10 |
| B-10.05 | Privacy policy and terms: a gap between the text and the real processing reported, a change drafted | a new processing, a change in law | 2 | publishing | UC-7.6, UC-15.5 |
| B-10.06 | Insurance and contracts: cover and terms checked against the business's current size | yearly | 2 | concluding | UC-4.17 |
| B-10.07 | Keeping the guardrails: a change written as a versioned proposal with its reason | a person asks | 2 | accepting it | UC-7.1, UC-6.13 |

### 4.11 Steering the agents

These are not processes of the business. They are what Taktus itself does for every process,
and without them no other process is safely autonomous.

| ID | What Taktus does | Level | Stays with a person | Rests on |
|---|---|---|---|---|
| B-11.01 | Heartbeat: every expected run reports its result (`ok`, `empty`, `error`) and duration; a run that does not happen raises an incident | 4 | — | UC-4.16 |
| B-11.02 | Budget guard: tokens, messages and money per process and month; paused at the budget | 4 | changing a budget | UC-8.5 |
| B-11.03 | A cap on open work: nothing new starts while open pull requests or started tasks are at the cap | 4 | changing the cap | UC-8.12 |
| B-11.04 | Stop: one process, an adapter or everything stopped, and the stop confirmed | 4 | — | UC-7.2 |
| B-11.05 | Raising and lowering: the correction rate per process and action computed, the request prepared | 2 | raising, lowering | UC-7.5, UC-7.1 |
| B-11.06 | Checking what was claimed: a step's report of completion checked against the record of its tool calls; the record is the truth | 4 | — | UC-6.1, ADR-0021, ADR-0024 |
| B-11.07 | Repetition: a step that repeats the same action in a loop is stopped | 4 | — | UC-8.12 |
| B-11.08 | Incident coordination: an incident opened, its timeline kept, processes assigned, a post-mortem drafted | 3 | communication outside | UC-6.8 |

---

## 5. The introduction path

The business runs today without Taktus. Taktus is introduced into it in six stages. **A stage
opens only when the previous one measurably holds** (UC-9.6). A stage that stops holding is
reported, and the processes it raised fall back by rule.

| Stage | Name | What is added | What people still do | Opens when | Milestone |
|---|---|---|---|---|---|
| 0 | The control loop | the daily report (B-9.01); first routines for pull requests, errors and triage (B-7.01, B-7.04, B-1.05) | read every day and intervene | the tenant is created and its first processes registered at level 1–2 | `0.4.0` |
| 1 | Operation without handwork | watchers for cost, errors, model credit, payment reconciliation, back office, deadlines (§4.1, §4.2, B-6.01, §4.5, B-10.01) | handle only deviations | stage 0 held for four weeks: the report ran every day, and every proposal was decided by a person | `0.5.0` |
| 2 | Customer contact on its own | support sends for approved classes itself, with a label, an independent check and evaluations as a gate (§4.3, §4.4) | approve classes, handle escalations | stage 1 held; no expected run missed without an incident | `0.6.0` |
| 3 | Release without people | rollout by corridor, deployment with smoke test and rollback (§4.8) | release the store submission and the release merge | stage 2 held; the correction rate of each approved class below its limit | `0.6.0` |
| 4 | Development end to end | from the customer's signal to the merged fix; a merge by an independent reviewing step under a written policy (§4.7) | the policy and the roadmap | stage 3 held; no rollback missed | `0.7.0` |
| 5 | The business runs dark | every process at its target level (§4) | goals, guardrails, budgets, liability, signature | stage 4 held | `1.0.0` |

"Held" is measured: each stage's condition is a rule over the ledger, and the tenant may make it
stricter, never looser than the catalogue's.

---

## 6. What stays with a person

At every stage, including stage 5. This is the tenant's anchor set (ADR-0008, UC-15.5). The
business may add to it. Taktus never runs with less.

| What stays | How Taktus keeps it |
|---|---|
| **Moving money:** refunds, prices, discounts, contracts, wages, advertising budget | a legal anchor on every step that moves money; Taktus prepares and gives reasons, a liable person carries it out |
| **Legal responsibility:** management, tax returns, data-protection impact assessments, processing agreements, answers to authorities and lawyers | a legal anchor (UC-15.5) |
| **Staff and partnerships** | a strategic anchor; and no figure about a person (principle 14) |
| **Its own limits:** guardrails, budgets and autonomy levels | no process changes a limit or a level; a raise needs a person (UC-7.1); a limit is changed by a person (ADR-0005); a fall is by rule (UC-7.5) |
| **Cheating to green:** changing tests, security rules, feature flags or acceptance criteria to make something pass | an action class at level 1 on every change to the paths the tenant declares protected; a step whose change touches one halts with a decision request |
| **Promises:** dates, features, legal advice | an outward message that promises one is held for a person (UC-7.6) |
| **Mass sending** without explicit approval | an outward action above the tenant's recipient limit is anchored (UC-7.6) |
| **User data** outside the specific case | a step sees only its case's data; an analysis step never speaks outward (UC-7.7) |

A breach of this list is an incident and lowers the process at once (UC-7.5).

---

## 7. What the catalogue asks of the tool

The catalogue lists thirteen requirements on the tool that carries it. Each is a use case of
Taktus.

| # | Requirement | Use case |
|---|---|---|
| 1 | Approval as a state of its own: a task waits for a role, with draft, reason and one-click release, also from chat or push | UC-7.1, UC-7.4, UC-6.11, #323, #331 |
| 2 | Autonomy per task type, raised and lowered by counted corrections | UC-7.1, **UC-7.5** |
| 3 | Agents as actors: identity, scope and budget of their own, separate from people in the audit | UC-1.7, UC-8.11, UC-7.3, UC-6.1 |
| 4 | Budgets per agent: tokens, messages and money per month; paused at the budget | UC-8.5 |
| 5 | Heartbeat and dead man's switch: an expected run that does not happen raises an incident | **UC-4.16** |
| 6 | A stop per agent and global, with confirmation | UC-7.2 (#436) |
| 7 | Evidence, not claims: every step carries its tool calls; the record is the truth | UC-6.1, ADR-0021, ADR-0024 |
| 8 | Intake from every source, de-duplicated by stable links back | UC-4.14, UC-1.1 |
| 9 | Scope and data separation: an analysis step reads much and never speaks outward; a service step sees only the sender's data | UC-7.3, **UC-7.7** |
| 10 | Deadlines and response limits as a rule of the tool, not a timer in every agent | **UC-4.17** |
| 11 | A history of figures, so that every corridor is computed against a median | **UC-6.13** |
| 12 | Corridors as configuration: yellow and red thresholds, versioned, changed only by a person | **UC-6.13** |
| 13 | A clean border to neighbouring systems | non-goals; UC-5.3, UC-6.8 |

The use cases in bold were written for this case (NTC-0210). So were UC-4.18 (evaluations as a
gate and against drift), UC-7.6 (outward messages), UC-8.12 (a cap on open work and a stop to
repetition) and UC-9.6 (the introduction path).

---

## 8. The capabilities it needs

Every outward access goes through an adapter named by capability (CLAUDE.md §6). Which system
serves each one is the tenant's (NEED-0028). Connectors over open standards are built before the
systems are known (#441). Many systems ship a server of their own on the protocol connectors
use; those become connector candidates (#410). A connector for each system the business names
follows (#447).

| Capability | For | Available |
|---|---|---|
| repository service: issues, pull requests, pipelines | §4.7, §4.8, B-1.11, B-1.12 | yes (`github` connector) |
| chat | the report, decision requests, steering | yes |
| mail and helpdesk: receive, draft, send | §4.3, B-10.03 | no |
| cloud billing export, monitoring and logs | §4.1 | no |
| error tracking | B-1.04, B-1.05, B-7.01 | no |
| payment providers and the product's entitlements | B-3.04, §4.6 | no |
| model providers' credit and use | B-2.01 | no |
| app stores: reviews, submission, beta, staged rollout | B-3.09, §4.8 | no |
| deployment targets with rollback | B-8.05, B-8.06 | no |
| customer system and feedback portal | B-5.05, B-3.07, B-9.04 | no |
| an analytics copy without personal fields | B-9.02, B-9.06 | no |
| accounting export | B-6.06, B-10.03 | no |
| a browser for synthetic flows | B-1.06, B-7.08, B-7.09 | a worker; not built |
| social media and forum search | B-3.10 | no |

---

## 9. When this case holds

`1.0.0` is complete only when all of the following hold (DEC-0199):

- the business installed its instance from the documentation, and upgraded it at every
  release since without losing a run and without the project's help (#445);
- every connector it uses is part of this repository and passes the conformance suite;
- every process of §4 is registered for the tenant and runs in production;
- every process has reached its target level, or Taktus has proposed the raise with the
  evidence UC-7.1 and UC-7.5 ask for; a person of the business may decline it;
- stage 5 of §5 is reached;
- every row of §6 is enforced: a test runs a level-4 process into each and finds it halted;
- every figure marked `exact` in §4 is produced by a `rule` or `statistics` step with a check;
- at least one step has matured from a language model to a trained model on Taktus's own
  proposal (B-3.01 is the first candidate);
- no document, name, amount or address of the business appears in this repository, a log of the
  project or the ledger's content.

---

## 10. Where the boundary lies

**Not the business's systems of record.** Taktus is not its helpdesk, customer system,
accounting or analytics (non-goals). **Not the business's liability.** What §6 keeps with a
person is not prepared into a decision Taktus takes. **Not a measure of anyone.** No process
assesses a named person, including the audit of privileged actions (principle 14). **Not the
`it-operations` blueprint.** The platform-operation case UC-02 stays at `2.0.0`; this case needs
only the infrastructure processes of §4.1.

---

## 11. Dependencies

The function-level use cases of §7 · the `dev-orchestration` blueprint (UC-01) · the second
tenant created by a command (#318) · the connectors of §8 · maturation (#218) · level 4
(`0.6.0`) · autonomy per action class in production use (`0.7.0`) · the legal-anchor catalogue
reviewed (DEC-0029) before money moves under §6.
