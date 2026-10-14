# NEED-0027 — A real operation for the second tenant

**Kind:** information
**Raised in:** the pull request that records DEC-0195, for issue #400
**Issue:** [#412](https://github.com/Jersyfi/taktus/issues/412)
**Needed by:** 2026-10-31
**Foreseeable since:** DEC-0195, where the owner decided that Taktus proves itself on a real operation rather than a second software project

## 1. What is needed

Data on the operation that becomes Taktus's second tenant. One of two ways:

- **Way 1:** a real business's complete use case. The owner expects to receive one by the end of
  October 2026. It should cover:
  - what arrives, such as invoices, enquiries or orders, and through which channel;
  - who decides what;
  - which systems are in use, such as accounting, mail or storage;
  - roughly how many cases arrive a week.
- **Way 2, plan B:** the owner's own household administration. This means where incoming
  documents arrive, which payments the owner releases, and the owner's agreement that a Taktus
  instance under the owner's control processes them.

## 2. Why

Taktus is to prove itself where it differs from software factories: an `exact` amount, a legal
anchor, and a step that matures from a language model to a trained model (DEC-0195, W1). That
needs a real operation with real cases.

## 3. By when

**2026-10-31.**

- If the business case is not there by then, #400 starts on 2026-11-01 with way 2.
- If the business case arrives later, it becomes the third tenant and carries the second domain
  (#402).
- If neither way is provided, `0.4.0` keeps its other conditions, and the second tenant stays
  open with this need.

## 4. How to provide it

1. Way 1: once the use case has arrived, tell the session where it is. Its content is never
   written into this repository.
2. Way 2: answer in the issue "NEED-0027: plan B". Name the channel your documents arrive
   through, for example a mailbox or a folder, without its address. A session then sets up the
   tenant with you.

## 5. What it must never be

Never a document, a name, an amount or an address of the operation in this public repository,
an issue, a log or a message to a session. Never sent to a model endpoint the tenant has not
configured. The data stays in the tenant's own instance. Access to a mailbox or a folder is a
credential, given only through the way `CREDENTIALS.md` describes.

## 6. What happens next

Answer in the issue with "NEED-0027: way 1" or "NEED-0027: plan B". The next session records it
and starts #400.

## 7. How to confirm

The issue carries the answer. Once #400 has started, the second tenant appears in the tenant
list of the instance (`taktusctl tenants list`, #318), by its display name only.

## Outcome

**Provided:** 2026-10-14
**Confirmed by:** the session read the business's catalogue on 2026-10-14: eleven areas, 96 use cases, autonomy stages, a path in six stages, a list of what stays with a person and thirteen requirements on the tool. The owner's answer is DEC-0199. The catalogue is not in this repository.
**How it was provided:** way 1, before the date. Plan B does not start. The catalogue names no systems and no volumes; these, the roles and where the tenant's instance runs are NEED-0028.
**Recorded in:** [#442](https://github.com/Jersyfi/taktus/pull/442)
