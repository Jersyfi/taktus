# The signing credentials connector — App Store Connect

The connector contract v1 ([`contracts/connector/v1`](../../../../../../contracts/connector/v1/README.md))
over the App Store Connect API: when a team's signing certificates and provisioning profiles
expire. Everywhere else it is the capability `expiry.credentials`. **It never reads a
certificate's or a profile's content.**

It is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.appstore --port 9125
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--target` is the
API's address (default `https://api.appstoreconnect.apple.com`). `--timeout` is the longest one
request may take, in seconds (default 30).

## What it declares

One operation of effect `read`, `expiry.credentials.list`. Every page is one unit.

| Input | Meaning |
|---|---|
| `kinds` | a list of `certificate` and `profile`, optional; both by default |
| `limit` | at most this many, 1 to 1000 (default 200) |

The output is `credentials`, the nearest expiry first, `complete` and `read_at`.

| Field | From |
|---|---|
| `kind`, `id` | `certificate` or `profile`, and the API's identifier |
| `name` | a profile's `name`; a certificate's **serial number** |
| `type` | `certificateType` or `profileType` |
| `platform` | `platform`: `IOS`, `MAC_OS` or `UNIVERSAL` |
| `state` | a profile's `profileState`, `ACTIVE` or `INVALID`; null for a certificate, which has none |
| `expires_at` | `expirationDate`, in RFC 3339 UTC |
| `days_left` | whole days from `read_at` to `expires_at`, rounded down; negative once expired |
| `key` | `credential:<kind>:<id>:<expires_at>`: a renewed one is a new key |

**No person is ever copied.** A development certificate's `name` and `displayName` are the
name of the person it was issued to, so neither is requested, and a certificate is named by
its serial number (principle 14).

## What it asks, and what it never asks

| Request | What for |
|---|---|
| `GET /v1/certificates?fields[certificates]=certificateType,serialNumber,platform,expirationDate&limit=200` | the certificates |
| `GET /v1/profiles?fields[profiles]=name,platform,profileType,profileState,expirationDate&limit=200` | the profiles |

The sparse fieldsets name every attribute read and no other. **`certificateContent` and
`profileContent` are never requested**, so the API never answers them. No endpoint that
downloads, creates, revokes or deletes anything is called. Each answer's `links.next`, where
present, is followed, at most ten pages for each kind, and only while it names the configured
address: the token goes nowhere else. A page cut by that bound, or an entry without an
`expirationDate`, makes the answer incomplete.

| The provider's answer | Cause |
|---|---|
| 400, 404 | `invalid` |
| 401 | `unauthenticated` |
| 403 | `forbidden` |
| 429, 5xx, no answer in time, no connection | `unavailable`, retryable |
| anything else | `unexpected` |

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `STORE_API_KEY` | actions: the **requesting identity's** team API key, one line `<issuer id>:<key id>:<base64 of the .p8 file>`, of a role that may read certificates and profiles | the file `TAKTUS_CREDENTIAL_STORE_API_KEY_FILE` names, read at the moment of each call, never stored |

The API does not take the key itself. It takes a JSON Web Token signed with it (ES256), whose
header names the key id as `kid` and `typ: JWT`, and whose payload names the issuer as `iss`,
`iat`, an `exp` 15 minutes later (the API admits at most 20) and `aud: appstoreconnect-v1`.
The connector signs one per call. The three parts are one value so that the operator writes
and rotates one file, and the parts cannot drift apart. The `.p8` file is the PEM the API's
key page offers once; `base64 -i AuthKey_<key id>.p8` gives the third part. A value that does
not parse, or a key that does not load, is `unauthenticated` before any request. An
individual API key, whose token carries `sub: user` instead of an issuer, is not supported.

The contract has no connector without the requesting identity's credential (C-03): a call
that references none is refused.

## Documentation it follows

- Generating Tokens for API Requests: https://developer.apple.com/documentation/appstoreconnectapi/generating-tokens-for-api-requests
- List and download certificates (`GET /v1/certificates`): https://developer.apple.com/documentation/appstoreconnectapi/get-v1-certificates
- List and download profiles (`GET /v1/profiles`): https://developer.apple.com/documentation/appstoreconnectapi/get-v1-profiles
- The resources' attributes: https://developer.apple.com/documentation/appstoreconnectapi/certificate/attributes-data.dictionary
  and https://developer.apple.com/documentation/appstoreconnectapi/profile/attributes-data.dictionary;
  paging: https://developer.apple.com/documentation/appstoreconnectapi/pageddocumentlinks

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9125/mcp --scenario connectors/taktus_connectors/appstore/scenario.json
```

[`scenario.json`](scenario.json) lists the certificates and profiles of the fake under
`tests/fakes/app_store_service.py`, and an unknown kind as the invalid call. It names no
write, and C-05 passes as not applicable. The fake verifies the token's signature, so the
credential's value must be a real key: `app_store_service.test_value()` makes one.
