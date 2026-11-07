# ADR-0205 — A helpdesk is read and written to only internally, and a help-centre article only as a draft

**Status:** accepted · extends ADR-0150 (connectors for the systems a business names) and
ADR-0024 (idempotency of outward operations) · issue #401, UC-03 B-3.01, B-3.11

## Context

UC-03 stage 2 asks two processes of a helpdesk. B-3.01 sorts the inbox: spam, bounces, cold
sales, tests and applications are recognised and closed without a reply. B-3.11 finds a
recurring question without an article and drafts one from answered cases; publishing stays with
a person (UC-03 §4.3, §6). No connector read a helpdesk; UC-03 §8 listed "drafts and a
helpdesk: no".

Helpdesks share no open standard. The two most widely used ones each publish a REST API over
tickets, comments and, for one of them, help-centre articles (ADR-0150: the most widely used
product per capability).

## Decision

### 1. Two capabilities

| Capability | Operations | Effect |
|---|---|---|
| `helpdesk.tickets` | `.list`, `.read` | read: a ticket with its subject, status, tags, comments' text and whether each is public; the requester by identifier only |
| | `.note` | write, `marked`: an internal comment ending with the call's key; a repeat finds it among the comments |
| | `.close` | write, `marked` by the tag itself: the ticket tagged and set solved |
| `helpcentre.articles` | `.list` | read: the articles of the help centre |
| | `.draft` | write, `marked` by a label derived from the key: an article created as a draft, never published, without notifying subscribers |

No operation writes a public reply to a customer. A reply goes through B-3.02's mail and its
message frame (UC-7.6). An internal note and a close are acts inside the business's own system;
a public word is not.

### 2. Two connectors, one shape

`zendesk/` serves both capabilities; `freshdesk/` serves `helpdesk.tickets` in the same shape,
statuses mapped to the first one's names. A bundle runs on either unchanged. Both take the
credential `HELPDESK_TOKEN`.

### 3. B-3.01: rules first, a model for the rest

The engine falls back from a model only to a person. The sorting therefore runs fixed rules
first: a bounce or a test is recognised by pattern and closed without asking a model. Only what
no rule recognised goes to a model, whose answer a rule holds to six classes. A request is
never closed. Every non-request is closed with the tag `sorted-<class>` at level 2, after a
person confirmed it. The model's labels are the history that UC-4.24 needs to propose a trained
model in its place: UC-03 §9 names B-3.01 the first candidate.

### 4. B-3.11: an independent check refuses a copy

A model drafts the article from solved tickets in its own words. No rule detects a copied
sentence, so an independent model step judges the draft original or copied, and a rule refuses
a copy. The draft is created unpublished at level 2.

## Alternatives

- **One generic helpdesk interface.** None exists; inventing one would serve no tenant.
- **The model first, a rule as its fallback.** A step's fallback is a person, not another
  method; the rules have to run before the model.
- **A public reply through the helpdesk.** It would bypass UC-7.6's message frame, which B-3.02
  already holds for mail.

## Consequences

- `connectors/taktus_connectors/zendesk/` and `freshdesk/`, their fakes, adapter tests and
  conformance entries; C-05 on every write.
- `blueprints/software-operations/processes/B-3.01-inbox-sorting.yaml` and
  `B-3.11-help-centre-gaps.yaml`, run in `tests/composition/test_software_operations_helpdesk.py`.

## Where this promise ends

- **The second helpdesk lists only tickets created in the last 30 days** and has no status
  filter; the connector filters what it read.
- **A close of an unassigned ticket may be refused** by the first helpdesk; it is `invalid`,
  and a person closes it.
- **Labels on an article need a plan that has them.** Without them a repeated draft is not
  found again and may be created twice.
- **The copy check is a model's judgement.** It can pass a paraphrase too close to an old
  answer; the person who publishes reads the draft.
- **B-3.01 starts at level 2.** Closing without a person is reached only through UC-7.1.
- **Proven against fakes of the published APIs**, not against a helpdesk the project runs
  (DEC-0225).
