# NTC-0293 — A reply reads the sender's account in a bundle of its own, and is noted on the helpdesk ticket

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-11-14
**Raised in:** the branch `area/tenant-connectors`, for DEC-0239
**How it follows:** DEC-0239 asks that the second tenant's template cover its catalogue, B-3.02's
account and subscription tools among it, with data of the sender only (UC-7.7) and without a
second source of truth. ADR-0130 fixes how a case's data is read: the scope's subject is an
input the run starts with, and a version whose scoped step may start without it is refused.
Principle 9 favours the smallest change that keeps that rule.

## 1. What was decided

- **A second bundle of B-3.02,** `B-3.02-draft-reply-account.yaml`, for a case whose customer the
  run is given. It requires `customer`. The product first says whether the message's sender is
  that customer's verified address. Only then are the account and the subscriptions read, each
  scoped to the customer, and shown to the draft and the check. An instance keeps one of the two
  bundles, as for B-8.04 and B-8.05.
- **B-3.02, version 6,** stays the bundle for a message alone. It takes an optional `ticket`, the
  helpdesk's ticket of the case, and adds the sent reply to it as an internal note.

## 2. The evidence

- **A message carries no customer identifier.** The payment provider's identifier is what the
  scoped reads need. The event of a received message gives the message only.
- **The scope rule refuses an optional subject.** Registration refused a draft of version 6 that
  read the account under an optional `customer`: "a case without its subject has no scope".
- **The helpdesk capability has no public reply.** `helpdesk.tickets` reads, notes internally and
  closes. A reply sent through the helpdesk would need a new outward operation under the message
  frame, which is more than this item.

## 3. What was considered

- **Make `customer` required in B-3.02.** Rejected: a run started by an arriving message could
  then not start, because the event has no customer.
- **Find the customer by the sender's address.** Rejected: the accounts manifest has no lookup by
  address, and a customer found by a step cannot be a scope's subject (ADR-0130).
- **Send the reply through the helpdesk.** Not built now: it needs `helpdesk.tickets.reply` in the
  manifest and in both helpdesk connectors, held by the message frame like the mail send.

## 4. Which entry permits it

M2.6. The owner may overrule it in the pull request.

## 5. The entry it proposes

**M2.15** — *A process that needs a case's subject which its start cannot give is served by a
second bundle of the same process that requires the subject, beside the bundle without it; an
instance keeps one. A scoped read never stands under an optional input (ADR-0130).*
