# DEC-0216 — The chart makes the egress gateway's key itself

**Category:** NON-BLOCKING
**Mode entry:** ADR-0028 (what a needs request asks of the owner is the owner's to accept)
**Raised in:** the session that took up the milestones `0.1.0` to `0.3.0`, on 2026-10-21
**Issue:** none; the owner answered in conversation
**Needed by:** 2026-10-31
**Written after the answer:** the owner answered in conversation on 2026-10-21; left out of the acceptance rate (DEC-0042).

## 1. What this is about

#324 replaces each job's egress proxy with one gateway of the instance (ADR-0115). The gateway admits a job by a token the runner signs with a key. NEED-0032 asked the owner to create that key as a Secret in both of the instance's namespaces before the next release.

## 2. Why you are being asked

A needs request asks the owner to act; whether the owner must act at all is the owner's to say (ADR-0028). The owner had said that an operator sets Taktus up once and Taktus steers the rest (DEC-0214).

**Sources checked:** ADR-0115, NEED-0032, DEC-0214.

## 3. What you must decide

Whether the owner creates the gateway's key, or the chart makes it.

## 4. What you need to know to decide

The key is a random value nobody outside the instance needs. Helm can draw it on the first install and read it back at every upgrade, so that a token signed before an upgrade still holds.

## 5. Options

### Option A — the chart makes the key and keeps it (recommended)

### Option B — the owner creates the Secret, as NEED-0032 asks

## 6. What is blocked

The next release on the instance.

## 7. How to answer

In conversation.

## Outcome

**Decided:** 2026-10-21
**Answer:** Option A. "NEED-0032 so umbauen" (the owner's words: rebuild NEED-0032 that way).
**Reasoning given:** none beyond the recommendation.
**What it changes:**

- `deploy/k8s/chart/templates/gateway-key.yaml` makes `<release>-gateway-key` in both namespaces on the first install and writes the same value at every upgrade. `execution.gateway.keySecret` stays for an operator who wants a key of their own.
- NEED-0032 is superseded and #546 closed. `CREDENTIALS.md` names no need for the key.

**Recorded in:** [#547](https://github.com/Jersyfi/taktus/pull/547)
