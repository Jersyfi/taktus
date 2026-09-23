# DEC-0024 — ADR-0025 asked how many instances, not who owns what runs

**Category:** DEFECT
**Raised in:** [#40](https://github.com/Jersyfi/taktus/pull/40), which records the target and writes the deployment plan
**Issue:** none; a defect is corrected, not asked (ADR-0017 §2)

## 1. What this is about

ADR-0025 answers one question: may an instance of Taktus run on infrastructure that it
administers itself? Its rule is right and stays: **no instance runs on infrastructure that it
administers itself**, because an instance that can break its own ground can break the path its
own repair would travel.

Its second section is where it slipped. "What is allowed" reads: *running on infrastructure
that a **different instance** administers is allowed, provided the running instance has its own
namespace, its own database and its own credentials.* Written that way, the permission is
granted only where a second Taktus instance is the administrator — and the ordinary case, by
far the most common one, is that **a person** administers the platform. A reader following the
ADR to the letter finds the rule forbidding self-administration, finds the permission covering
a case that does not apply, and finds nothing at all about theirs.

The target decision of 2026-09-23 (DEC-0023) is exactly that case: the owner administers a
k3s cluster; Taktus is given two namespaces in it and administers nothing. Allowed by §1,
unmentioned by §2.

The same section carries a second, quieter confusion. Its three conditions are about where the
boundary is — a namespace, a database, credentials — and they read as though the number of
clusters were the subject. It is not. The subject is *who administers what runs, and whose
code and whose data are inside it.* A second cluster is one way to draw a boundary and never
the thing the rule is about.

## 2. Why you are being asked

You are not. The ADR permits an arrangement in §1 and fails to describe it in §2, which is a
contradiction inside one document. Entry M1.4 of `docs/decisions/anchors.taktus.md` makes the
correction the session's, recorded here; where an ADR is involved the record is an amendment in
the ADR, which is what this is.

## 3. What you must decide

Nothing. The rule does not change. What changes is that §2 now says who may administer the
infrastructure — anyone that is not this instance, which includes a person — and that the
conditions are about the boundary and not about a count of clusters.

## 4. What you need to know to decide

- **What did not change:** §1, the rule itself. An instance still never runs on infrastructure
  it administers. *Administers* still means holding credentials that can change the
  infrastructure and running processes that use them; reading its state is not administering
  it, and deploying a workload into a namespace one was given is not either.
- **What the correction adds:** that the administrator may be a person, an organisation or
  another instance, and that the three conditions — a boundary of one's own, a database of
  one's own, credentials that reach nothing outside it — are what makes the arrangement safe,
  whoever the administrator is.
- **Why it matters beyond wording:** the next question of this kind is meant to be answered by
  §1 without a new decision (the ADR says so). A §2 that covers one administrator out of three
  sends the reader back to asking.

## 5. Options

None for the owner. What the session did: amended ADR-0025 §2 so that the permission names any
administrator other than the instance itself, said that the conditions are about the boundary
rather than the number of clusters, and added a consequence pointing at DEC-0023 as the worked
example. §1, §3 and §4 are untouched, and *Where this promise ends* gains the limit the
correction exposes: the rule still cannot see a credential that is broader than its holder
knows, and it says nothing about who else's workload shares the platform.

## 6. What is blocked

Nothing.

## 7. How to answer

Nothing to answer. To object: "Reopen DEC-0024" in an issue, with the reading you hold.

## Outcome

**Corrected:** 2026-09-23
**What was wrong:** ADR-0025 §2 permitted running on infrastructure that *a different instance*
administers, and named no other administrator — so the ordinary case, a platform a person
operates, was permitted by §1 and described nowhere. The section's three conditions also read
as though the subject were how many clusters there are.
**Why it was wrong:** the ADR exists so that the next placement question is answered from the
rule instead of from scratch. A permission that covers one administrator out of three sends
the reader back to asking, which is the thing the ADR was written to stop.
**What it now says:** the permission is to run on infrastructure administered by anyone that is
not this instance — a person, an organisation, or another instance — under the same three
conditions, which are about the boundary the instance is given and not about a count of
clusters. DEC-0023 is named as the worked example: one cluster, two namespaces, administered
by the owner.
**What changed in substance:** nothing the software does, and nothing the rule forbids. One
arrangement that was already allowed is now also described.
**Recorded in:** [#40](https://github.com/Jersyfi/taktus/pull/40)
