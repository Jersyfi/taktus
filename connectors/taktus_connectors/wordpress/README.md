# The website connector — the WordPress REST API

`website.posts` over the REST API WordPress serves under `/wp-json/`: a post drafted, read, and
published once a person released it. WordPress is the most widely used system for running a
website (ADR-0150). This directory, this file and the configuration that points at it are the
only places in the repository that name the product. Everywhere else it is `website.posts`
(ADR-0212).

```
uv run python -m taktus_connectors.wordpress --port 9136 --target https://www.example.org
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
site's address; the API answers under `<target>/wp-json/wp/v2/`. A site that serves the API
only through `?rest_route=`, without pretty permalinks, is not reached. Point `--target` at the
fake under `tests/fakes/website_service.py` to run without a network.

The documentation followed: the
[Posts reference](https://developer.wordpress.org/rest-api/reference/posts/) — list with
`slug`, `status`, `context` and `per_page`, create, retrieve and update at
`POST /wp/v2/posts/<id>` — and [Authentication](https://developer.wordpress.org/rest-api/using-the-rest-api/authentication/):
application passwords over HTTP Basic, in WordPress since 5.6.

## What it declares

| Operation | Effect | Idempotency | What it does, and how a repeat is recognised |
|---|---|---|---|
| `website.posts.read` | read | — | `GET /wp/v2/posts/<id>?context=edit`: `id`, `status` (WordPress's word: `publish`, `future`, `draft`, `pending`, `private`), `title` as rendered, `link`, `modified` |
| `website.posts.draft` | write | marked | `POST /wp/v2/posts` with `title`, `content` (HTML) and an optional `excerpt`, status `draft`: nothing is published. The slug is `taktus-` and the first 16 hexadecimal digits of the SHA-256 of the idempotency key. Before creating, the posts with that slug are asked for in every status a draft can reach, in the `edit` context: one found is the original, replayed. Output `id`, `status`, `link`, `slug` |
| `website.posts.publish` | write | marked | `POST /wp/v2/posts/<id>` with status `publish`. The post's status is its own mark: one already published reports `replayed`. **Weaker than a key, and stated so**: a repeat after somebody else published it reports replayed too. A post a person scheduled (`future`) is `conflict`, and stays scheduled |

A person who publishes the draft by hand may change its slug; the draft's repeat after that
finds nothing and drafts again. A repeat comes from a retry of the same run, minutes later, so
this is stated rather than guarded.

How the API's answers map to the contract's causes is the table in
[`operations.py`](operations.py): 400 `invalid`, 401 `unauthenticated`, 403 `forbidden`, 404
`not_found`, 429 and 5xx `unavailable`. Only the error's `code` is passed on. Consumption is
counted in `quota` units named `requests`.

## Credentials

One, `WEBSITE_TOKEN`: `<user name>:<application password>` of a site user with the role that
may create and publish posts — an *Author* publishes their own posts, an *Editor* any
(`CREDENTIALS.md`). It is referenced by name in the context of every call and read at the
moment of the call from the file `TAKTUS_CREDENTIAL_WEBSITE_TOKEN_FILE` names. The connector
has no credential of its own. A value without a colon is `unauthenticated` before the site is
asked.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9136/mcp --scenario connectors/taktus_connectors/wordpress/scenario.json
```

[`scenario.json`](scenario.json) reads the post 1, drafts a post twice under one key and once
under another, and asks for an identifier that is no number. Against a real site it creates
drafts and publishes nothing: point it at a staging site. Publishing's repeat, marked by the
status, is proven by `tests/adapters/connectors/test_website_connector.py`, not by the suite.
