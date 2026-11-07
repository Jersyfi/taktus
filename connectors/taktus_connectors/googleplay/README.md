# The store reviews connector of the second store — the Google Play Developer API

The connector contract v1 ([`contracts/connector/v1`](../../../contracts/connector/v1/README.md))
over the reviews of the Google Play Developer API. This directory, this file and the
configuration that points at it are the only places that name the product. Everywhere else it
is the capability `stores.reviews` (ADR-0207), in the same operations and shapes as the first
store's connector, [`appstore/`](../appstore/README.md).

It is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.googleplay --port 9147
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address, `https://androidpublisher.googleapis.com` by default, and `--token-url` the token
endpoint, `https://oauth2.googleapis.com/token`. Point both at the fake under
`tests/fakes/review_replies_service.py` to run without a network; `--token-url /token` takes
the path on `--target`. Added to an instance by one entry of `TAKTUS_CONNECTORS`:
`stores.reviews=http://store-reviews-connector:9147/mcp`. An instance with both stores names
one connector per tenant's app; one capability resolves to one connector.

## The documentation it follows

- [reviews](https://developers.google.com/android-publisher/api-ref/rest/v3/reviews): the
  Review resource, `comments` with `userComment` and `developerComment`.
- [reviews.list](https://developers.google.com/android-publisher/api-ref/rest/v3/reviews/list):
  `maxResults`, `token`, `tokenPagination.nextPageToken`.
- [reviews.get](https://developers.google.com/android-publisher/api-ref/rest/v3/reviews/get).
- [reviews.reply](https://developers.google.com/android-publisher/api-ref/rest/v3/reviews/reply):
  `replyText`, about 350 characters at most; a reply to a review that has one updates it.
- [Reply to reviews](https://developers.google.com/android-publisher/reply-to-reviews): only
  reviews with a text, written or changed in the last week; 200 reads an hour and 2,000 replies
  a day per app.
- [Using OAuth 2.0 for server to server applications](https://developers.google.com/identity/protocols/oauth2/service-account):
  the signed statement, RS256, and its exchange at the token endpoint.

## What it declares

The three operations of `stores.reviews` the first store's connector declares, with the same
inputs and the same fields per review. Where this store differs:

- **What is listed.** The store answers only reviews that carry a text and were written or
  changed in the last week. An older review, and a rating without a text, are not readable
  through the API (the console's export holds them). A process that runs at least weekly sees
  every new review with a text.
- **Ratings.** The store filters by no rating; the connector keeps the `ratings` asked for
  itself, after reading each page.
- **Fields.** `title` and `territory` are null: the store gives neither. `language` is the
  reviewer's language, `version` the app version the review was written on, `at` when the
  review last changed. The author's name, the device and its metadata are never copied.
- **Reply.** At most 350 characters, as the store admits; a longer text is `invalid` before
  the store is asked.

`stores.reviews.reply` is `marked` by its own text, as the first store's is: the connector reads
the review, and a reply whose text is the new one is replayed without a second call. Weaker than
a key, and stated so: a repeat after somebody else wrote the same text reports replayed too. A
reply of another text is `conflict` unless `replace` is true.

The causes are the first store's: `invalid`, `not_found`, `unauthenticated` (also a token
endpoint that refuses the key, or a credential that is no key file), `forbidden`,
`unavailable` and retryable, `unknown` on a write whose answer did not arrive. The store's
message is never copied into an error: only its status token is (`operations.py`).

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `STORE_REVIEWS_ACCOUNT` | actions: the **requesting identity's** service account key file, JSON as the console hands it out, of an account the store's console grants "Reply to reviews" for the app, and nothing else | the file `TAKTUS_CREDENTIAL_STORE_REVIEWS_ACCOUNT_FILE` names, read at the moment of each call, never stored |

The connector signs a statement with the key and exchanges it at the configured token endpoint
— never at the `token_uri` the file names — for an access token, which it keeps in memory by the
key's digest until a minute before it expires. Each exchange counts as a request.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9147/mcp --scenario connectors/taktus_connectors/googleplay/scenario.json
```

[`scenario.json`](scenario.json) is the first store's, with this store's package name and
review. `--fault C-05` writes without reading the reply in place, so that a repeat is not
recognised; `tests/conformance/test_connector_v1_business.py` runs every fault.
