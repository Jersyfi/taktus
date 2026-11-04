# The expiry connector — certificates over TLS, domains over RDAP

The connector contract v1 ([`contracts/connector/v1`](../../../contracts/connector/v1/README.md))
over two open standards: the certificate a TLS endpoint presents in its handshake (RFC 8446,
RFC 5280), and a domain's registration over the Registration Data Access Protocol (RFC 9082,
RFC 9083). Everywhere they are the capabilities `expiry.certificates` and `expiry.domains`
(ADR-0196). The expiry watcher B-1.09 of the blueprint `software-operations` reads both.

It is proof and example, not a requirement: the control plane runs with it removed.

```
uv run python -m taktus_connectors.expiry --port 9120 \
    --certificate www.example:443 --certificate api.example:443 \
    --target https://rdap.registry.example
```

serves MCP over streamable HTTP at `/mcp` and readiness at `GET /health`. `--certificate`
names a TLS endpoint, `host:port` or `host` for 443, that a call may read; a call that names
another is refused before any connection. `--target` is the RDAP server's base address.
`--ca-file` adds an authority the verification trusts beside the system's store. `--timeout` is
the longest a read waits, in seconds (default 30). Added to an instance by entries of
`TAKTUS_CONNECTORS`: `expiry.certificates=http://expiry-connector:9120/mcp` and
`expiry.domains=http://expiry-connector:9120/mcp`.

## What it declares

| Operation | Effect | Input | Output |
|---|---|---|---|
| `expiry.certificates.read` | `read`, two handshakes at most | `host`, `port` (default 443) | `subject`, `issuer`, `names`, `serial`, `not_before`, `not_after`, `read_at`, `days_left`, `trusted`, `verify_failure`, `key` |
| `expiry.domains.read` | `read`, one request | `domain`, in its ASCII form | `domain`, `handle`, `expires`, `registered`, `last_changed`, `status`, `read_at`, `days_left`, `key` |

`days_left` is the whole days from `read_at` to the expiry, rounded down, negative once it has
passed; a registration without an `expiration` event answers `expires` and `days_left` null.
`key` names the thing and its expiry moment: a process marks what it filed with it, and a
renewal is a new key.

A certificate is read even when it does not verify — expired, for another name, from an
unknown authority — and answers `trusted: false` with the verification's reason. An endpoint
that cannot be reached is `unavailable`. The RDAP server's answers map as `operations.py`
documents: 400 `invalid`, 401 `unauthenticated`, 403 `forbidden`, 404 `not_found`, 429 and 5xx
`unavailable`, any other `unexpected`.

## Credentials

| Name | Purpose | How it reaches the connector |
|---|---|---|
| `EXPIRY_TOKEN` | actions: the **requesting identity's** bearer token for the RDAP server (RFC 7481 §3.2); a public server ignores it, and then any value of the operator's serves | the file `TAKTUS_CREDENTIAL_EXPIRY_TOKEN_FILE` names, read at the moment of each call, never stored |

A TLS handshake sends no credential. `CREDENTIALS.md` describes it.

## Conformance

```
uv run taktusctl conformance run --contract connector/v1 \
    --endpoint http://127.0.0.1:9120/mcp --scenario connectors/taktus_connectors/expiry/scenario.json
```

[`scenario.json`](scenario.json) reads a domain of the fake RDAP server under
`tests/fakes/expiry_service.py`; it names no write, and C-05 passes as not applicable.
`--fault NAME` breaks exactly one check (`connectors/serving.py`);
`tests/conformance/test_connector_v1_business.py` runs every fault. The certificate read is
proven against the fake's TLS endpoints in `tests/adapters/connectors/test_expiry_connector.py`.
