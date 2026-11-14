# NTC-0294 — The event catalogue gains `error.created`, `payment.failed` and `subscription.changed`

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-11-14
**Raised in:** the branch `area/tenant-connectors`, for DEC-0239
**How it follows:** DEC-0239 asks that processes which poll be started by the systems' events
where a signed intake can take them. `contracts/events/v1` §6 says a new kind is added to v1
and breaks nothing; ADR-0048 makes a kind of the catalogue the only thing a trigger can name.

## 1. What was decided

The kind `error.created` joins the catalogue of `contracts/events/v1`: an error tracker opened a
new issue. Its context requires `project` and `error`, the tracker's identifier of the issue, and
carries `link` where the tracker gives one. The error tracking connector produces it (ADR-0331).

Two more kinds join it (ADR-0337): `payment.failed`, a payment provider reported a customer's
payment failed, context `customer` and `payment`; and `subscription.changed`, a payment provider
or an in-app subscription service reported a subscription started, renewed, changed, cancelled
or ended, context `customer`, `subscription` and, where given, `change`. Both are produced by
two sources each, in one shape, so that a process reads either source unchanged.

## 2. The evidence

- **The repository service's `issue.opened` is another subject.** It names a repository and an
  issue number; a tracker's issue is an error group in a project. One kind for both would let a
  trigger meant for one start on the other.
- **The contract admits the addition.** §6: "A new kind or a new condition is added to v1 and
  breaks nothing." `make gate-contracts` and `make gate-compat` pass.

## 3. What was considered

- **Reuse `issue.opened` with a filter on the channel.** Rejected: the context it requires,
  `repository` and `issue`, does not describe an error.
- **Name it `error_issue.created`.** Rejected: the subject is the error; the tracker's word for
  its group stays in its connector.

## 4. Which entry permits it

M2.6. The owner may overrule it in the pull request.

## 5. The entry it proposes

**M2.16** — *A system's event whose subject no kind of the events catalogue names becomes a kind
of its own in v1, named by its subject and what happened, never a reuse of a kind whose context
describes another subject (`contracts/events/v1` §6).*
