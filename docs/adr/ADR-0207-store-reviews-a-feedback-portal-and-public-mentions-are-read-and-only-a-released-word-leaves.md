# ADR-0207 — Store reviews, a feedback portal and public mentions are read, and only a released word leaves

**Status:** accepted · extends ADR-0150 (connectors for the systems a business names), ADR-0142
(the message frame) and ADR-0024 · issue #401, UC-03 B-3.07, B-3.09, B-3.10

## Context

Three processes of UC-03 stage 2 meet the public. B-3.09 answers store reviews: a reply
drafted, tied to a known bug, released by a person. B-3.07 takes a customer's feature wish into
a feedback portal with the customer's consent, or counts a vote. B-3.10 finds mentions on social
media and in forums and sorts them into support case, praise and criticism; answering in public
stays with a person (UC-03 §4.3, §6). UC-03 §8 listed all three as "no".

## Decision

### 1. Four capabilities

| Capability | Operations | Effect |
|---|---|---|
| `stores.reviews` | `.list`, `.read` | read: rating, title, text, territory, language, moment, version where given, whether answered; never the reviewer |
| | `.reply` | write, `marked` by its own text: a repeat with the same text writes nothing; a response of another text is a `conflict` unless `replace` is set, so a person's answer is never overwritten |
| `feedback.posts` | `.list` | read: posts without their author |
| | `.create` | write, `marked` by a digest of the key in the post's details |
| | `.vote` | write, `marked` by the vote itself |
| `mentions.search` | `.query` | read: id, address, text, moment, source; never the author |

### 2. The connectors

`appstore/` and `googleplay/` serve `stores.reviews` in one shape, under one credential
`STORE_REVIEWS_KEY`: the first signs a short-lived token with the business's key, the second
exchanges a service account's signed statement for a token. `canny/` serves `feedback.posts`
(`FEEDBACK_TOKEN`). `mastodon/` and `discourse/` serve `mentions.search` in one shape
(`MENTIONS_TOKEN`).

### 3. The processes

- **B-3.09**, level 2: a review of one or two stars without a response is read with the open
  issues; a model names the issue it reports, held by `match` to an issue that exists; a model
  drafts the reply, an independent step checks it, a rule holds money and a promise for a
  person, and the reply is sent through `stores.reviews.reply` only after a person released it,
  under UC-7.6's frame.
- **B-3.07**, level 2: a model reads the wish from a support message; every write runs only
  when the run's input `consent` is exactly `yes`, the customer's own answer. Then a vote on the
  post the model named, or a new post, after a person confirmed it.
- **B-3.10**, level 1: a model sorts each mention into a class held by `extract`; the result is
  the list of ids per class, never a count per author. Nothing is posted.

## Alternatives

- **The reviewer's name kept for the reply.** No step needs it; what is not read cannot leak.
- **Consent read by a model from the conversation.** A misread consent publishes a customer's
  words; the input is explicit and its value exact.
- **One connector per process for mentions.** A capability resolves to one connector; a second
  source is a second configuration.

## Consequences

- Five connector directories, fakes, adapter tests and conformance entries; C-05 on every write.
- Three bundles, run in `tests/composition/test_software_operations_stores.py` and
  `test_software_operations_community.py`.

## Later

- 2026-11-07: `stores.reviews` is served by the connector `appstores` under `STORES_KEY`, the store chosen per call by `platform`; `appstore/` and `googleplay/` were folded into it (ADR-0210, Later). The decision above is unchanged.

## Where this promise ends

- **No pattern across releases is found.** No rule groups a reading by a field, and the first
  store gives no app version.
- **No store announces a new review.** The tenant starts each run of B-3.09 from a listing.
- **The second store serves only the last week's reviews with text**, and a reply of at most
  350 characters.
- **One mentions source per configuration.** A capability resolves to the first connector that
  declares it; a business that searches both a social network and a forum runs a configuration
  for each.
- **Full-text search on the social network depends on the server's search backend.**
- **B-3.07 checks the post the model named only for its form.** The portal and the confirming
  person check that it is the right post.
- **The feedback portal's key is not narrower than the whole portal.** The portal offers none.
- **Proven against fakes of the published APIs** (DEC-0225).
