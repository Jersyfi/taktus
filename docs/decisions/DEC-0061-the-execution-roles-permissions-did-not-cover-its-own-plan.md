# DEC-0061 — The execution Role did not cover its own plan

**Category:** DEFECT
**Raised in:** [#119](https://github.com/Jersyfi/taktus/pull/119), while building the cluster execution adapter (#65)
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

`deploy/k8s/README.md` contradicted itself about what Taktus's own service account may do in
the execution namespace. Section 1 granted jobs (create, get, list, watch, delete), and pods and
their logs (get, list), and "nothing else, anywhere". Section 7, the specification of the
cluster execution adapter, and issue #65 require the adapter to create a Secret with the job's
credentials for the job's lifetime, an egress proxy pod, and a Service for the unit and one for
the proxy, and to delete them again. None of that is possible with section 1's list.
`CREDENTIALS.md` and NEED-0007 repeated section 1's narrower sentence.

## 2. Why you are being asked

You are not. The repository contradicted itself, which is entry M1.4 of
`docs/decisions/anchors.taktus.md`. What the adapter must do is fixed by section 7 and the issue;
the correction makes section 1 grant what that requires, and not more.

## 3. What you must decide

Nothing.

## 4. What you need to know to decide

- **What section 1 now grants**, in the execution namespace only: jobs as before; pods and
  `pods/log` as before; `secrets` with `create` and `delete`; `services` with `create` and
  `delete`. The client of the adapter carries the same list (`PERMITTED` in
  `src/taktus/adapters/driven/execution/kubernetes/api.py`) and refuses any other call before
  sending it; the unit tests fail the adapter on any call outside it.
- **What was kept narrow on the way.** No `get` or `list` on secrets: Taktus can write a job's
  credentials into the namespace and can never read one back. No `pods` `create`: the egress
  proxy runs as a Job, which is still a pod of its own as section 6 requires, so the existing
  permission on jobs covers it. No `patch` or `update` on anything.
- **What follows from `create` on secrets.** A Secret of a certain type asks the cluster for a
  token of a service account in the same namespace. Section 1 therefore now requires that no
  service account in the execution namespace holds a Role, the one jobs run as included, so
  that such a token opens nothing.
- **What did not change.** The deployment identity of NEED-0007 already holds every one of
  these permissions in the execution namespace, which the cluster requires of whoever creates
  the Role. The chart (#64) renders the Role from section 1; it needs no new value.

## 5. Options

None for the owner.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0061" in an issue. A narrower Role would mean
changing what section 7 and #65 require — credentials from a Secret, a Service per unit — and
that is a decision request, not this correction.

## Outcome

**Corrected:** 2026-10-08
**What was wrong:** section 1 of `deploy/k8s/README.md` granted Taktus's service account jobs,
pods and logs only, while section 7 of the same file requires it to create and delete Secrets,
Services and a proxy.
**Why it was wrong:** section 1 was written for "create jobs and read their logs" before
section 7 worked out how credentials and the egress proxy reach a job.
**What it now says:** section 1 lists every resource and verb, with what each is for: jobs;
pods and logs read-only; Secrets and Services create and delete; never a read of a Secret; no
Role for any account in the namespace. `CREDENTIALS.md` and NEED-0007 say the same.
**What changed in substance:** nothing that was required; the Role the chart will render is the
one section 7 already needed.
**Recorded in:** [#119](https://github.com/Jersyfi/taktus/pull/119)
