# The wiki connector — a wiki of shelves, books and pages

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
implemented against the REST interface of BookStack, the wiki the owner chose for the guides
(DEC-0176, NEED-0021). This directory, this file and the configuration that points at it are
the only places in the repository that name the product. Everywhere else — processes,
blueprints, documents — it is the capability `knowledge.pages` (ADR-0065 §4). Another tenant's
knowledge system is configuration, and another connector serves the same capability.

It is a knowledge system, not a requirement: with it removed the guides go to the directory the
instance serves where one is configured (`TAKTUS_KNOWLEDGE_DIRECTORY`), and nowhere otherwise.

```
uv run python -m taktus.adapters.driven.connectors.bookstack --port 9102 --target <base address>
```

serves MCP over streamable HTTP at `http://127.0.0.1:9102/mcp` and readiness at `GET /health`.
`--target` is the wiki's base address, without `/api`; the connector knows no default, and the
address of the owner's wiki is in the private note, never in this repository. Point it at the
fake under `tests/fakes/wiki_service.py` to run without a network.

**Adding it to an instance** is one entry of `TAKTUS_CONNECTORS`:
`knowledge.pages=http://knowledge-connector:9102/mcp`. The run's connector pool then finds
`knowledge.pages` in its declaration, and S-05 publishes the guides into the wiki. Nothing under
`src/taktus/components/` changes (`tests/adapters/connectors/test_guides_wiki.py`).

## What it declares

The resource `taktus://connector/v1/capabilities` ([`declaration.py`](declaration.py)):

| Operation | Effect | Idempotency | Input | Output |
|---|---|---|---|---|
| `knowledge.pages.list` | read | — | `place` of one to three names | `pages`: every page at or below the place, each with `place`, `digest` and `mark` |
| `knowledge.pages.read` | read | — | `place` of three names | `place`, `body`, `digest`, `mark`; `not_found` where no page is |
| `knowledge.pages.write` | write | marked | `place` of three names, `body`, `mark`, `expected` | `place`, `digest`; `conflict` where the page does not hold `expected`, or a page is there when `expected` is `null` |

`digest` is the SHA-256 of a page's text as UTF-8, written `sha256:<hex>`. A write's record is
the page, `knowledge.page` with the wiki's identifier of it.

Consumption is counted in `quota` units named `requests`, in a window of 60 seconds, the unit
the wiki's rate limit is stated in. Every result reports how many requests the call made. A
call's `demand` is its most: a list at most 70 — two to find the shelf and its books, at most two
listings of 500 pages per book for at most four books, and one read per page for at most 60
pages; a read at most 5; a write at most 8. A list over a place with more books or pages is
refused as `invalid`, never cut short.

## How a place maps onto the wiki

A place is a list of names: **shelf, book, page**. A guide's place in the manifest is a shelf and
a book (`docs/guides/guides.yaml`: `Taktus` / `Administration`, `Taktus` / `Using Taktus`), and
its pages are the third level.

- A **list** takes one, two or three names: a shelf, a book on it, or one page.
- A **read** and a **write** take exactly three.
- A name is matched exactly, as written.
- A place the wiki cannot hold is refused as `invalid` **before any request**: more than three
  names, fewer than the operation needs, an empty name, a name with spaces at either end (the
  wiki trims names, so it would never match), a control character, or more than 255 characters.
- Two shelves of one name, two books of one name on a shelf, or two pages of one name in a book
  make the place ambiguous; the call ends `conflict` and changes nothing.
- A page inside a **chapter** has no place, because a place has no level for a chapter. It is not
  listed, read or written. A page the connector creates is never in a chapter.
- Shelves and books are made by a person in the wiki (NEED-0021). A write into a shelf or a book
  that does not exist ends `not_found`; the connector only creates and changes pages.

## What it keeps beside a page

The wiki keeps a list of **tags**, names and values, on every page, and returns them unchanged
with the page. A write puts four kinds there, every name beginning with `taktus-`:

| Tag | What it holds |
|---|---|
| `taktus-key-0`, `-1`, … | the idempotency key of the write that put the text there |
| `taktus-mark-0`, `-1`, … | the mark (ADR-0065 §3) |
| `taktus-digest` | the digest of the text written |
| `taktus-stored` | the digest of the text as the wiki stored it |

The key and the mark are split into numbered parts of at most 160 characters, each part URL-safe
base64: a tag's value is short, and a wiki may trim it. A person's own tags on the page stay as
they are through every write. A person who removes Taktus's tags makes the page one Taktus did
not write: it is then `foreign` and never overwritten (ADR-0065, *where this promise ends*).

**A wiki that changes the text it stores does not make a page look edited.** A wiki may change a
page's text on the way in: line endings, spaces at the end of a line, the last newline. The
connector reads the stored text back from the wiki's answer to the write. Where it differs from
what was written, the connector writes the tags once more, with `taktus-stored` set to the digest
of the stored text. On reading, a page whose text still hashes to `taktus-stored` was not touched
since: its `digest` is `taktus-digest`, the digest of what was written. A page whose text hashes
to anything else was edited, and its `digest` is that of the text as it stands; its mark is
unchanged, so the knowledge component measures it `edited` and keeps it (ADR-0065 §5).

The text of a page is its Markdown. A person who edits a page in the wiki's visual editor
empties its Markdown; the page is then read as its HTML, and so as edited.

**A write that expects a digest** reads the page, compares its digest with `expected`, and
writes. The wiki has no conditional write, so this is two moves: a person who saves the page
between the read and the write loses that save. The window is the length of one request. This
is the bound the directory connector has too (ADR-0065, *where this promise ends*).

**A repeat** is a write whose key the page already carries, with the digest of the same text. It
writes nothing and answers `replayed`.

## Credentials

One, referenced by the name below, created and mapped by the operator; `CREDENTIALS.md`
describes it as a parameter, under NEED-0021:

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `KNOWLEDGE_TOKEN` | actions: the token of the wiki's user `Taktus`, `<id>:<secret>`, sent as `Authorization: Token <id>:<secret>` | referenced in the call's context. For a reference `injected_as: env`, read from the file `TAKTUS_CREDENTIAL_KNOWLEDGE_TOKEN_FILE` names; for `injected_as: file`, from the path the reference gives. At the moment of the call; never stored |

**Never from the environment.** A variable holding the value itself is not read, because a
process listing shows variables: a call whose file is missing ends `unauthenticated`. The
connector has no token of its own. A call that references no credential, or one with no file,
ends `unauthenticated` without a request.

What the user needs in the wiki, and no more (NEED-0021): a role with the system permission
*Access system API* alone, and on each book the guides go to, and on the live test's scratch
book, *View*, *Create* and *Update* — never *Delete*. Without them a write ends `forbidden`.

## Errors

The wiki answers a fault with its HTTP status ([`api.py`](api.py)): 401 is `unauthenticated`,
403 `forbidden`, 404 `not_found`, 409 `conflict`, 422 and every other 4xx `invalid`, 429 and 5xx
`unavailable`, which may be retried. A connection that could not be made, and a read that was
not answered in time, are `unavailable` with no effect. A write that was sent and never answered
is `unknown` with effect `unknown`. The wiki's own words stay out of `detail`.

## Faults

`--fault NAME` makes the connector break exactly one conformance check, so that the suite can be
shown to catch it ([`faults.py`](faults.py)); `--list-faults` prints them. The connector has no
intake, so C-07 and C-08 have no fault and pass as not applicable. `make gate-conformance` runs
the suite against every fault and expects exactly that check to fail
(`tests/conformance/test_connector_v1_knowledge.py`).

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9102/mcp \
    --scenario src/taktus/adapters/driven/connectors/bookstack/scenario.json
```

[`scenario.json`](scenario.json) is written for the fake: its shelf `Scratch`, book
`Conformance` and page `Seeded page` exist there from the start, and the text the suite writes
ends with spaces and a carriage return, which the fake changes as a wiki may. Against the real
wiki the live test writes the scenario for its scratch book — the book `Live test` on the shelf
`Taktus live test`, which holds nothing else — and then publishes the guides into their two
books (`tests/adapters/connectors/test_knowledge_live.py`), in the workflow `live`, monthly and
by dispatch on `main` (DEC-0048). It runs once NEED-0021 is provided. The role may delete
nothing, so every run leaves a handful of pages in the scratch book; a person deletes them when
they want.
