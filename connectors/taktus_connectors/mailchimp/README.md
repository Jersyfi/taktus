# The newsletter connector — the Mailchimp Marketing API

`newsletter.broadcasts` over the Mailchimp Marketing API 3.0: a campaign to one audience
drafted, read, and sent once a person released it. Mailchimp is the most widely used service
for sending a newsletter to a list (ADR-0150). This directory, this file and the configuration
that points at it are the only places in the repository that name the product. Everywhere else
it is `newsletter.broadcasts` (ADR-0212).

```
uv run python -m taktus_connectors.mailchimp --port 9135 --target https://us6.api.mailchimp.com
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
address of the account's API: the data centre the account lives in, the part of the API key
after its dash. Point it at the fake under `tests/fakes/newsletter_service.py` to run without a
network.

The documentation followed:
[Campaigns](https://mailchimp.com/developer/marketing/api/campaigns/) — list, add, get and the
send action ([send](https://mailchimp.com/developer/marketing/api/campaigns/create-action-send.md));
[Set campaign content](https://mailchimp.com/developer/marketing/api/campaigns/upsert-content.md);
[Errors](https://mailchimp.com/developer/marketing/api-concepts/errors.md); and the
authentication of
[Send your first API request](https://mailchimp.com/developer/marketing/build/start-developing/send-your-first-api-request.md):
HTTP Basic, any user name, the API key as the password.

## What it declares

| Operation | Effect | Idempotency | What it does, and how a repeat is recognised |
|---|---|---|---|
| `newsletter.broadcasts.read` | read | — | `GET /3.0/campaigns/<id>`: `id`, `web_id`, `status` (the API's word: `save`, `schedule`, `sending`, `sent` and the others it names), `list`, `recipients` (the API's `recipient_count`, the audience's size), `emails_sent`, `send_time` |
| `newsletter.broadcasts.draft` | write | marked | `POST /3.0/campaigns`, type `regular`, to the audience `list`, with `subject`, `from_name` and `reply_to`; then `PUT /3.0/campaigns/<id>/content` with `text` as the plain text and `html` as given, or the text's paragraphs escaped into HTML. Nothing is sent. The campaign's internal title, which recipients never see, is `taktus-` and the first 24 hexadecimal digits of the SHA-256 of the idempotency key. Before creating, the audience's campaigns are listed, a thousand per page, ten pages at most: one with the title is the original, replayed |
| `newsletter.broadcasts.send` | write | marked | `POST /3.0/campaigns/<id>/actions/send`, the whole audience. The campaign's status is its own mark: one that is `schedule`, `sending` or `sent` is not sent again and reports `replayed`. **Weaker than a key, and stated so**: a repeat after somebody else sent it reports replayed too. A campaign the API holds not ready to send is `invalid`, with the API's error title |

**No recipient leaves the service.** No output names a member of the audience or an address;
the audience is its identifier and its size. Whether a send reaches more recipients than the
tenant allows without a person's word is the process's anchor (UC-7.6), read from `recipients`.

A draft whose content could not be set after the campaign was created reports `unknown`; its
repeat finds the campaign by its title and does not set the content again. A person sees the
empty draft in the service.

How the API's answers map to the contract's causes is the table in
[`operations.py`](operations.py): 400 `invalid`, 401 `unauthenticated`, 403 `forbidden`, 404
`not_found`, 405 `conflict`, 429 and 5xx `unavailable`. Consumption is counted in `quota` units
named `requests`.

## Credentials

One, `NEWSLETTER_TOKEN`: an API key of a user of the account who may create and send campaigns
(`CREDENTIALS.md`). It is referenced by name in the context of every call and read at the
moment of the call from the file `TAKTUS_CREDENTIAL_NEWSLETTER_TOKEN_FILE` names. The connector
has no key of its own.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9135/mcp --scenario connectors/taktus_connectors/mailchimp/scenario.json
```

[`scenario.json`](scenario.json) reads the campaign `c-seeded`, drafts a campaign to `list-1`
twice under one key and once under another, and asks for an identifier the API cannot hold.
Against a real account it creates drafts in the audience it names, and sends nothing: point it
at a test audience. The send's repeat, marked by the status, is proven by
`tests/adapters/connectors/test_newsletter_connector.py`, not by the suite.
