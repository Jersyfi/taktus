# ADR-0268 — A headless content store serves `website.posts`: a draft document a person publishes

**Status:** accepted · extends ADR-0212 (release texts drafted, sent and published by a person)
and ADR-0024 (idempotency) · UC-03 §4.8, DEC-0228

## Context

B-8.08 drafts the release's post on the website and publishes it on a person's decision, through
`website.posts`. Its one connector writes to a site that renders its own pages. Many software
businesses keep their site's content in a headless content store instead, which a separate front
end renders. The most widely used publishes an HTTP API of documents, mutations and actions. A
draft there is a document whose identifier starts with `drafts.`; publishing replaces the
published document with the draft and removes the draft.

## Decision

### 1. The operations of the website connector, over documents

A connector `sanity` serves `website.posts.read`, `.draft` and `.publish` with the website
connector's inputs and outputs, under `WEBSITE_TOKEN`, so that B-8.08 runs unchanged.

### 2. The key is the document's identifier

A draft's identifier is `drafts.taktus-` and a digest of the idempotency key. It is created with
`createIfNotExists`, after the published and the draft identifier were read. A document found is
the original, `replayed`. The write is `marked`, and the mark is the document itself.

### 3. Publishing is the store's own action

`website.posts.publish` runs the store's publish action, held to the draft's revision as read. A
post published with no draft left reports `replayed`. A draft changed in between is a
`conflict`. The process holds the step for a person at every level; the connector only does
what that person released.

### 4. The schema is the tenant's

A post is a document of a type with a title, a slug and a body. The body is Portable Text, built
from the post's HTML. The type and the field names are arguments of the connector, because a
store's schema is the business's own.

## Alternatives

- **A patch of the published document.** Readers would see a text no person released.
- **A draft named by the store.** A repeat would have to search for it by its content.

## Consequences

- Connector `sanity`, its fake `tests/fakes/content_lake_service.py`, scenario and image;
  `WEBSITE_TOKEN` names it in `CREDENTIALS.md`, a project's token of the role Editor.
- B-8.08 is proven against it (`tests/composition/test_software_operations_connectors2.py`).

## Where this promise ends

- **A schema other than the arguments name is not served.** A required field the connector does
  not write makes the store's front end, not the connector, refuse the post.
- **The HTML is reduced to the block type's defaults.** A link keeps its text only, and a
  script is dropped.
- **A post scheduled through the store's own releases is not seen.** The read sees documents,
  and such a post reads as a draft.
- **The fake follows the published reference.** Nothing was run against the service.
