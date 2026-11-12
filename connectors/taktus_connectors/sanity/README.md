# The second website connector — the Sanity HTTP API

`website.posts` over the Sanity HTTP API: a post drafted as a draft document, read, and
published once a person released it. Sanity is among the most widely used headless content systems,
where a website's posts live apart from the site that shows them (ADR-0150). It serves the
operations the WordPress connector (`wordpress/`) serves, under the same names, with the same
inputs and the same output fields, so that B-8.08 runs on either. This directory, this file and
the configuration that points at it are the only places in the repository that name the
product. Everywhere else it is `website.posts` (ADR-0212, ADR-0268).

```
uv run python -m taktus_connectors.sanity --port 9183 --target https://abc123.api.sanity.io \
    --dataset production --studio https://example.sanity.studio
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. Point `--target` at
the fake under `tests/fakes/content_lake_service.py` to run without a network.

| Argument | Default | Meaning |
|---|---|---|
| `--target` | — | the project's API address, `https://<project id>.api.sanity.io` |
| `--dataset` | `production` | the dataset the posts live in |
| `--api-version` | `v2025-02-19` | the API's dated version; the publish action needs `v2024-05-23` or later |
| `--type` | `post` | the document type of a post |
| `--title-field`, `--slug-field`, `--body-field`, `--excerpt-field` | `title`, `slug`, `body`, `excerpt` | the fields of the post type the connector writes |
| `--studio` | none | the Studio's address; a post's `link` opens it there. Without it, `link` is empty |

**The schema is the tenant's.** A Sanity dataset has no post type of its own: the tenant's
Studio defines it. The connector writes the convention most schemas start from — a string
title, a slug, the body as Portable Text and a string excerpt. A tenant whose fields carry other
names names them with the four arguments; a schema whose body is not Portable Text, or that
requires fields the connector does not write, is not served, and the draft fails the Studio's
validation where a person sees it.

The documentation followed:
[Mutation](https://www.sanity.io/docs/http-reference/mutation) — `POST
/<version>/data/mutate/<dataset>`, `createIfNotExists`, `returnIds`, `visibility`;
[Doc](https://www.sanity.io/docs/http-reference/doc) — `GET /<version>/data/doc/<dataset>/<ids>`,
`documents` and `omitted`;
[Actions](https://www.sanity.io/docs/http-reference/actions) — `POST
/<version>/data/actions/<dataset>`, `sanity.action.document.publish` with `publishedId`,
`versionId` and `ifVersionRevisionId`, and its statuses;
[Block type](https://www.sanity.io/docs/studio/block-type) — the default styles, lists and
decorators of Portable Text; the [Portable Text
specification](https://github.com/portabletext/portabletext); and
[Studio edit intent links](https://www.sanity.io/docs/visual-editing/studio-edit-intent-links)
for `<studio>/intent/edit/id=<id>;type=<type>`.

## What it declares

| Operation | Effect | Idempotency | What it does, and how a repeat is recognised |
|---|---|---|---|
| `website.posts.read` | read | — | `GET doc/<dataset>/<id>,drafts.<id>`: `id`, `status` (`draft` while a draft exists, else `publish`, the words the WordPress connector answers), `title` of the draft where there is one, `link`, `modified` (`_updatedAt`) |
| `website.posts.draft` | write | marked | `POST mutate/<dataset>`, `createIfNotExists` of the draft document `drafts.<id>` of the post type, with the title, the slug, the content as Portable Text and an optional excerpt: nothing is published. `<id>` is `taktus-` and the first 24 hexadecimal digits of the SHA-256 of the idempotency key, and the slug the same. Before creating, the published document and its draft are asked for by it: either found is the original, replayed. Output `id`, `status`, `link`, `slug` |
| `website.posts.publish` | write | marked | `POST actions/<dataset>`, `sanity.action.document.publish` of `drafts.<id>` onto `<id>`, locked on the draft's revision as read. A post published with no draft left is its own mark and reports `replayed`. **Weaker than a key, and stated so**: a repeat after somebody else published it reports replayed too. A draft a person changed between the reading and the publish is `conflict`, and stays a draft |

**Content.** `content` is HTML, as the processes write it. Paragraphs, headings `h1` to `h6`,
quotations and list items become blocks of the block type's defaults; `strong`, `em`, `code`,
`u` and `s` their decorators. A link keeps its text and loses its address; a script or a style
keeps nothing; any other element keeps its text ([`portable.py`](portable.py)).

**Identifiers.** A post's `id` is its published identifier: letters, digits, dashes and
underscores. One with a dot — a path, among them `drafts.` — is `invalid`; the connector names
the draft itself.

What WordPress does that this API does not: **a scheduled post.** WordPress holds a post a
person scheduled as `future`, and its publish is `conflict`. Scheduling here is a content release
of the Studio, a version of its own that the reading of the document and its draft does not
show; a post a person scheduled that way is
still a draft to this connector, and B-8.08's publish asks a person first at every level.

How the API's answers map to the contract's causes is the table in
[`operations.py`](operations.py): 400 `invalid`, 401 `unauthenticated`, 403 `forbidden`, 404
`not_found` (no such dataset, no draft to publish, or an API version before the actions), 409
`conflict`, 429 and 5xx `unavailable`. The API documents no error body; only the status is read.
Consumption is counted in `quota` units named `requests`.

## Credentials

One, `WEBSITE_TOKEN`, the same parameter as the WordPress connector's, so that B-8.08 runs
unchanged: here an API token of the project with the role *Editor*, which may read drafts and
create and publish documents — nothing more (`CREDENTIALS.md`). It is sent as `Authorization:
Bearer`, referenced by name in the context of every call and read at the moment of the call from
the file `TAKTUS_CREDENTIAL_WEBSITE_TOKEN_FILE` names. The connector has no token of its own.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9183/mcp --scenario connectors/taktus_connectors/sanity/scenario.json
```

[`scenario.json`](scenario.json) reads the post `post-1`, drafts a post twice under one key and
once under another, and asks for an identifier the API cannot hold. Against a real project it
creates drafts and publishes nothing: point it at a staging dataset. Publishing's repeat, marked
by the state, is proven by `tests/adapters/connectors/test_content_lake_connector.py`, not by
the suite.
