# The feedback portal connector — the Canny API

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
over the posts and votes of the Canny API. This directory, this file and the configuration that
points at it are the only places that name the product. Everywhere else it is the capability
`feedback.posts` (ADR-0207).

It is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.canny --port 9148
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address, `https://canny.io` by default; point it at the fake under
`tests/fakes/feedback_service.py` to run without a network. Added to an instance by one entry of
`TAKTUS_CONNECTORS`: `feedback.posts=http://feedback-connector:9148/mcp`.

## The documentation it follows

The API reference, <https://developers.canny.io/api-reference>: every request is a `POST` with a
JSON body carrying the secret key as `apiKey`. The connector uses `posts/list` (`boardID`,
`authorID`, `search`, `skip`, `limit`; answer `posts` and `hasMore`), `posts/create`
(`authorID`, `boardID`, `title` of at most 400 characters, `details` of at most 10,000; answer
`id` and `url`), `users/retrieve` (exactly one of `email`, `id`, `userID`), `votes/create`
(`postID`, `voterID`; answer `success`, whether the vote was created or already existed) and the
v2 `votes/list` (`postID`, `limit` 1 to 100, `cursor`; answer `items`, `hasNextPage`, `cursor`).
The reference states status 429 for a throttled key and gives error bodies `{"error": "..."}`;
it states no status for a refused key or an unknown object, so the connector maps by status
class (`operations.py`), and the fake's 401 for a refused key is the fake's choice, stated in
its docstring.

## What it declares

| Operation | Effect | Input | Output |
|---|---|---|---|
| `feedback.posts.list` | `read` | `board`, optional `search`, `limit` (default 100, at most 1000) | `posts`, each `id`, `board`, `title`, `details`, `status`, `score`, `url`; `count`; `complete` |
| `feedback.posts.create` | `write`, `marked` | `board`, `email` of the customer, `title`, `details` | `id`, `url`, `board` |
| `feedback.posts.vote` | `write`, `marked` | `post`, `email` of the customer | `post`, `counted` |

A created post's details end with `[ref taktus-<digest>]`, a digest of the idempotency key, not
the key. Before creating, the connector reads the customer's own posts on the board
(`authorID`) and finds the reference there; a repeat creates nothing and reports `replayed`.

A vote is its own mark. The portal holds one vote per customer and post, and `votes/create`
answers alike whether it counted a new one or found one. So before voting the connector reads
the post's votes and looks for the customer's: found, nothing is sent and the result reports
`replayed`. That is weaker than a key and stated so: a call after the customer voted by other
means reports `replayed` too. For the same reason the scenario names no vote — a new key on
the same customer and post cannot act again, which C-05 asks — and
`tests/adapters/connectors/test_feedback_portal_connector.py` proves the vote's repeat instead.

The customer is named by e-mail address, because that is what support knows; `users/retrieve`
turns it into the portal's user. A customer the portal does not know is `invalid`: the connector
never creates a portal user, whose required name is personal data no step needs. The address,
a post's author and a vote's voter are never copied into an output.

A refused or unknown request is `invalid`, a refused key `unauthenticated`, one without the right
`forbidden`, a throttled or failing portal `unavailable` and retryable. A write whose answer did
not arrive is `unavailable` with effect `unknown`, retryable: the next attempt's lookup finds
what it made. The portal's message is never copied into an error.

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `FEEDBACK_TOKEN` | actions: the portal's secret API key of the requesting identity | the file `TAKTUS_CREDENTIAL_FEEDBACK_TOKEN_FILE` names, read at the moment of each call, never stored |

The portal has one secret key per company, with every right of the API; no narrower key exists.
The key goes to the configured API and nowhere else. `CREDENTIALS.md` describes it.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9148/mcp --scenario connectors/taktus_connectors/canny/scenario.json
```

[`scenario.json`](scenario.json) lists the fake's board, creates a post for a customer the fake
knows (C-05), and lists a board it does not know as the call the portal refuses. `--fault NAME`
breaks exactly one check (`connectors/serving.py`); `tests/conformance/test_connector_v1_business.py`
runs every fault.
