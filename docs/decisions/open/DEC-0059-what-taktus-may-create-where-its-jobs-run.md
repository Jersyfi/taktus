# DEC-0059 — What Taktus may create where its jobs run

**Category:** NON-BLOCKING
**Raised in:** [#118](https://github.com/Jersyfi/taktus/pull/118), which builds the chart (issue #64)
**Issue:** [#113](https://github.com/Jersyfi/taktus/issues/113)
**Needed by:** 2026-10-20
**Provisional answer:** Option C. The chart grants exactly what issue #64 verifies: jobs, and reading their pods and logs. The cluster execution adapter (#65) is built against that; on the cluster it refuses a job that needs a credential or an allowed host, with the reason. Marked in `deploy/k8s/README.md` §1 and §10.

## 1. What this is about

On the cluster, Taktus runs each piece of foreign work — a coding agent's task, say — as a
**job**: a container started for that task alone, in a namespace kept for such jobs, and removed
when the task ends. Taktus itself runs in a namespace of its own, under an identity of its own
on the cluster, a **service account**. What that identity may do in the jobs' namespace is
written down as a **role**.

The deployment plan says two different things about that role.

- Its first section grants the least: create jobs, read their pods and their logs. Nothing else.
  The task that built the chart (#64) repeats this as the check it must pass: a role "granting
  exactly jobs and pods/log in the execution namespace".
- Its seventh section describes how the cluster adapter runs a job. Each job gets its
  credentials as a cluster **Secret** created for that job. Each job gets an **egress proxy** of
  its own — a second container that lets the job reach the hosts its task names and no others —
  and a **Service**, the cluster's stable address for reaching it. Creating a Secret, a proxy
  and a Service is exactly what the first section's role does not permit.

The chart now grants what the first section says. The adapter, built in parallel (#65), needs
what the seventh section says. Both cannot hold.

## 2. Why you are being asked

The question is how much Taktus may do on the infrastructure it runs on, for an instance you
have declared production (DEC-0057). The repository's two statements of it disagree, and the
task's own check fixes the narrower one. A session does not adjust the check of the task it
implements in order to pass it (CLAUDE.md §11, point 13); it argues the failure here. No entry
of `docs/decisions/anchors.taktus.md` names permissions on the platform.

**Sources checked:** `docs/vision/` — principle 12, production-ready, and the principle of
least privilege under it, which both options below satisfy in different measure; ADR-0025, which
forbids an instance to administer its infrastructure and is not touched by either option,
because both stay inside the jobs' namespace and change nothing Taktus itself runs on; ADR-0002's
execution table, which requires isolation and does not say how; both anchor pages, where no entry
covers it; the register — DEC-0023 asks for "the container boundary done properly", including a
host list that is enforced, and DEC-0057 makes the instance production. None of them chooses
between the two sections.

## 3. What you must decide

What Taktus's service account may create in the jobs' namespace.

## 4. What you need to know to decide

- **Why a Secret per job.** A job's credential must reach it as a file, never as a variable
  (`CREDENTIALS.md`). On a cluster the one way to put a file into a container that Taktus did
  not build is a Secret mounted into it. Without it a job runs without credentials.
- **Why a proxy and a Service per job.** A job that may reach "the repository service and the
  model provider" needs a filter by name. The cluster's own network rules filter addresses, not
  names (`deploy/k8s/README.md` §6). The proxy filters by name; the network rules make sure the
  job can reach nothing but the proxy. Without it, a job that names hosts is refused.
- **What the coding worker needs.** Both: a credential and a host list. With the narrow role,
  the coding worker cannot run on the cluster at all.
- **What a wider role risks.** Everything stays inside the jobs' namespace, where nothing
  permanent lives. A Secret Taktus creates there holds a credential Taktus already holds. A
  compromised control plane could create pods there; the namespace's admission policy
  (`restricted`) still forbids root, host access and added privileges.
- **A narrower way to the same end.** The proxy can itself run as a job, which the role already
  permits. Then only Secrets and Services are added, and Taktus never creates a bare pod.

## 5. Options

### Option A — jobs, Secrets and Services; the proxy runs as a job (recommended)

- **Meaning:** the role also grants `create`, `get` and `delete` on Secrets and Services, in the
  jobs' namespace only. The adapter starts the proxy as a job, not as a bare pod.
- **Consequence:** the coding worker runs on the cluster with its credential as a file and its
  host list enforced. Taktus can create no bare pod and nothing outside that namespace. The
  chart's check changes from "exactly jobs and logs" to "exactly jobs, logs, Secrets and
  Services", and the plan's first and seventh sections say the same.
- **Effort:** an hour in the chart and its test; the adapter (#65) follows the proxy-as-a-job
  shape.
- **Reversibility:** cheap: a role is a file in the chart.
- **Why recommended:** it is the least that makes the seventh section work, and it keeps the
  rule that Taktus never starts a pod outside a job.

### Option B — as the seventh section is written: also bare pods

- **Meaning:** the role also grants creating and deleting pods, Secrets and Services in the
  jobs' namespace.
- **Consequence:** the adapter is built as planned. Taktus can start a pod there that is not a
  job, with no deadline and no limit set by a job.
- **Effort:** an hour in the chart and its test.
- **Reversibility:** cheap.

### Option C — keep the role as it is

- **Meaning:** jobs, and reading their pods and logs. Nothing else.
- **Consequence:** the adapter refuses every job that needs a credential or an allowed host.
  The coding worker does not run on the cluster; it runs only as it does today, outside it.
- **Effort:** none.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing is blocked now. The chart merges with the provisional answer, Option C. The adapter is
built and tested against a fake of the cluster either way. What waits is the coding worker
running on the deployed instance: until this is answered, its jobs are refused there. Needed by
2026-10-20, with the install (#66). If no answer arrives by then, the instance is installed
without the coding worker on the cluster.

## 7. How to answer

"DEC-0059: Option A.", "DEC-0059: Option B." or "DEC-0059: Option C."
