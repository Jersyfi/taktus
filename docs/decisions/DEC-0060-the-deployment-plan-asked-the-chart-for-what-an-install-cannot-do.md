# DEC-0060 — The deployment plan asked the chart for what an install cannot do

**Category:** DEFECT
**Raised in:** [#118](https://github.com/Jersyfi/taktus/pull/118), while building the chart (issue #64)
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

The deployment plan, `deploy/k8s/README.md`, asked the chart for two things that an install
cannot do.

- **It said the chart renders both namespaces**, with their admission labels (§1, §2, §4). A
  namespace is an object of the cluster as a whole. The identity that installs Taktus may not
  create one: that is how it was provided (NEED-0007), and its outcome records that the two
  namespaces were created outside the chart, with their labels. A chart that renders them fails
  on its first install.
- **It said the migrations run as a hook before the install** (`pre-install`, §2). When the chart
  deploys the database itself (`database.deploy: true`, DEC-0032), nothing of the install exists
  before that hook runs — the database neither. A migration before the install has no database
  to migrate, and the install fails.

## 2. Why you are being asked

You are not. The repository says something that is not so, which is entry M1.4 of
`docs/decisions/anchors.taktus.md`. Nothing that runs changes: the chart did not exist before
this correction.

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

- The chart renders the namespaces only when asked (`namespaces.create: true`), for a cluster
  where the installing identity may. By default it renders into two namespaces that exist, and
  the plan says the admission labels are set where they are created.
- The migrations run before every upgrade, as planned. On the first install they run before
  anything starts where the database exists already, and right after the database is created
  where the chart deploys it. Until then the roles refuse to start against an empty schema and
  are restarted.

## 5. Options

None for the owner.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0060" in an issue.

## Outcome

**Corrected:** 2026-10-08
**What was wrong:** the plan had the chart create both namespaces with their labels, and run the
migrations before the install, also when the install creates the database.
**Why it was wrong:** the plan was written on 2026-09-23, before the deployment identity existed
and before the database decision; neither constraint was known.
**What it now says:** the namespaces exist before the install and carry their labels from
whoever created them; the chart renders them only on request. The migrations run before every
upgrade, and on the first install after the database the chart creates (`deploy/k8s/README.md`
§2, §4).
**What changed in substance:** nothing that runs; the chart is built to the corrected plan.
**Recorded in:** [#118](https://github.com/Jersyfi/taktus/pull/118)
