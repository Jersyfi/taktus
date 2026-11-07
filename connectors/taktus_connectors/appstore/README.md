# The store reviews connector — the App Store Connect API

The connector contract v1 ([`contracts/connector/v1`](../../../contracts/connector/v1/README.md))
over the customer reviews of the App Store Connect API. This directory, this file and the
configuration that points at it are the only places that name the product. Everywhere else it
is the capability `stores.reviews` (ADR-0207). The connector of the second store,
[`googleplay/`](../googleplay/README.md), declares the same operations in the same shapes, so
that a process runs on either.

It is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.appstore --port 9146
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address, `https://api.appstoreconnect.apple.com` by default; point it at the fake under
`tests/fakes/customer_reviews_service.py` to run without a network. Added to an instance by one
entry of `TAKTUS_CONNECTORS`: `stores.reviews=http://store-reviews-connector:9146/mcp`.

## The documentation it follows

- [List all customer reviews for an app](https://developer.apple.com/documentation/appstoreconnectapi/get-v1-apps-_id_-customerreviews):
  `GET /v1/apps/{id}/customerReviews`, `filter[rating]`, `sort`, `include=response`, `limit` at
  most 200, `links.next`.
- [Read customer review information](https://developer.apple.com/documentation/appstoreconnectapi/get-v1-customerreviews-_id_):
  `GET /v1/customerReviews/{id}`, `include=response`.
- [Create or update a response to a customer review](https://developer.apple.com/documentation/appstoreconnectapi/post-v1-customerreviewresponses):
  `POST /v1/customerReviewResponses`, which overwrites a response in place.
- [CustomerReview.Attributes](https://developer.apple.com/documentation/appstoreconnectapi/customerreview/attributes-data.dictionary),
  [CustomerReviewResponseV1.Attributes](https://developer.apple.com/documentation/appstoreconnectapi/customerreviewresponsev1/attributes-data.dictionary),
  [ErrorResponse](https://developer.apple.com/documentation/appstoreconnectapi/errorresponse).
- [Generating tokens for API requests](https://developer.apple.com/documentation/appstoreconnectapi/generating-tokens-for-api-requests):
  ES256, `kid`, `iss`, `iat`, `exp` at most twenty minutes on, `aud` `appstoreconnect-v1`.

## What it declares

Three operations of `stores.reviews`.

`stores.reviews.list`, `read`:

| Input | Meaning |
|---|---|
| `app` | the app's identifier at the store, its digits |
| `ratings` | the ratings to keep, a list of 1 to 5; every rating when absent |
| `limit` | how many reviews at most, 1 to 2000 (default 200); at most 20 pages of 200 are read |

The output is the `app`, its `reviews`, newest first, and `complete`, which says whether every
review fit within `limit`.

`stores.reviews.read` takes `app` and `review`, a review's identifier, and answers one review.

Each review is reduced to these fields, the same as the second store's:

| Field | Meaning |
|---|---|
| `id` | the review's identifier |
| `rating` | 1 to 5 |
| `title`, `text` | what the reviewer wrote |
| `territory` | the store's territory, ISO 3166-1 alpha-3 |
| `language` | null: this store gives none |
| `at` | when it was written |
| `version` | null: this store gives no app version with a review |
| `responded`, `response` | whether a response is in place, and its text |

The reviewer's nickname is never copied: no reply needs it, and what is not read cannot leak.

`stores.reviews.reply` is a write, `marked`. It takes `app`, `review`, `text` and `replace`
(default false), and publishes the text as the review's public response. The store keeps one
response per review and replaces it on a second POST. Before writing, the connector reads the
review: a response whose text is the reply's is the original, and the call is replayed
without a second POST. The text is its own mark, weaker than a key, and stated so: a repeat
after somebody else wrote the same text reports replayed too. A response of another text is
somebody's answer and is refused as `conflict`, unless `replace` is true. The record is
`store.review.response`, the review and the text's digest. The store publishes a response
after a while (`PENDING_PUBLISH`); `state` reports what it answered.

A request the store refuses is `invalid`, a review or app it does not know `not_found`. A key
it does not admit, or a credential that is no key, is `unauthenticated`, and a role without
the right `forbidden`. A throttled or failing store is `unavailable` and retryable. A write
whose answer did not arrive is `unknown`, effect `unknown`: a repeat finds the text. The store's
message is never copied into an error: only its error code is (`operations.py`).

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `STORE_REVIEWS_KEY` | actions: the **requesting identity's** API key, `<issuer id>:<key id>:<base64 of the .p8 file>`, of a key whose role may read reviews and write responses (Customer Support), and nothing else | the file `TAKTUS_CREDENTIAL_STORE_REVIEWS_KEY_FILE` names, read at the moment of each call, never stored |

The connector signs a token with the key for every request, valid fifteen minutes, and keeps
neither. The operator writes the file from the key App Store Connect hands out once, for
example `printf '%s:%s:%s' "$ISSUER" "$KEY_ID" "$(base64 < AuthKey.p8 | tr -d '\n')"`.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9146/mcp --scenario connectors/taktus_connectors/appstore/scenario.json
```

[`scenario.json`](scenario.json) lists the reviews of one and two stars of the fake, replies
to one with a fresh text and `replace`, so that each write is new, and reads a review by an
identifier the connector refuses. `--fault C-05` writes without reading the response in place,
so that a repeat is not recognised; `tests/conformance/test_connector_v1_business.py` runs every
fault.
