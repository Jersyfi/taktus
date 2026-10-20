# DEC-0215 — The instance runs two runs at once, and three tasks go to Taktus again

**Category:** NON-BLOCKING
**Mode entry:** DEC-0197 (handing a task to Taktus); the owner's act on a server (ADR-0028)
**Raised in:** the session that took up the milestones `0.1.0` to `0.3.0`, on 2026-10-20
**Issue:** none; the owner answered in conversation
**Needed by:** 2026-10-20
**Written after the answer:** the owner answered in conversation on 2026-10-20; left out of the acceptance rate (DEC-0042).

## 1. What this is about

Five tasks handed at once on 2026-10-20 overloaded the instance's one node. The runner missed its health check and was restarted, and #317's unit was lost with it. #394's unit did not start within 120 s. #325's pipeline failed when the CI runner's container engine answered 500 (#520).

## 2. Why you are being asked

Handing a task to Taktus is the owner's (DEC-0197). Installing the instance again is an act on its server.

**Sources checked:** DEC-0197, DEC-0205, DEC-0214.

## 3. What you must decide

Whether the runner's places drop from four to two, and whether #317, #325 and #394 go to Taktus again.

## 4. What you need to know to decide

Each coding unit takes 1.5 GiB and an egress proxy of its own on the same node. With two places, a third run waits in the queue instead of starving the runner.

## 5. Options

### Option A — two places; the three handed again once the instance runs with them (recommended)

### Option B — four places; hand them one at a time

## 6. What is blocked

#317, #325 and #394.

## 7. How to answer

In conversation.

## Outcome

**Decided:** 2026-10-20
**Answer:** Option A. "Zu 2 ja, Concurrency musst du für mich erledigen und hast die freigabe dafür." (the owner's words: to 2, yes; the session sets the concurrency for the owner, with the owner's approval).
**Reasoning given:** none beyond the recommendation.
**What it changes:**

- The instance's private values set `TAKTUS_RUNNER_CONCURRENCY: "2"`, and the session installs the same release (rc.27) again.
- #317, #325 and #394 are handed to Taktus again after that, their failed attempts' branches deleted first (DEC-0205).

**Recorded in:** this pull request
