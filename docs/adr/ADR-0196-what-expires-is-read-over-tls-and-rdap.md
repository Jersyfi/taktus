# ADR-0196 — What expires is read over TLS and RDAP

**Status:** accepted · extends ADR-0111 (connectors over open standards) and ADR-0158 (every
connector is an image of its own) · serves UC-03 B-1.09, UC-4.17 · issue #437

## Context

UC-03 B-1.09 asks that the things of the business that expire — domains, certificates, keys,
signing certificates, provisioning profiles, secrets — be listed 30 days before they expire.
Two of them are answered by open standards, whatever product the business uses.

- A **TLS server certificate** is sent by the server in every handshake (RFC 8446). Its X.509
  validity (RFC 5280) states the moment after which it is no longer valid. Anyone who can open
  a connection to the server reads it; no account is needed.
- A **domain's registration** is published by its registry over the Registration Data Access
  Protocol, RDAP (RFC 9082 for the query, RFC 9083 for the answer). The answer carries the
  registration's events, among them `expiration`. RDAP replaces the free text of WHOIS with JSON.

No connector of this repository read either. B-1.09 was listed as not built.

## Decision

### 1. One connector, `expiry`, with two capabilities

`connectors/taktus_connectors/expiry/` serves:

| Operation | Effect | What it reads |
|---|---|---|
| `expiry.certificates.read` | `read` | the certificate a configured TLS endpoint presents: subject, issuer, the names it covers, its validity, whether it verifies, and the whole days left |
| `expiry.domains.read` | `read` | a domain's registration at the configured RDAP server: its expiration, registration and last change, its status, and the whole days left |

Both answer `key`, a text that names the thing and its expiry moment. A process files a thing
once by marking what it filed with that key (ADR-0192 §1). A renewed certificate has a new
moment, so its next expiry is filed again.

### 2. The connector reaches only what it is configured for

A call names an endpoint by `host` and `port`. The connector admits only the endpoints its
configuration lists (`--certificate host:port`). A process cannot make it open a connection to
any other host. The RDAP server is configured too (`--target`); a call names only the domain.

### 3. The certificate is read even when it does not verify

An expired certificate, or one for another name, is exactly what the watcher must report. The
connector first opens a verifying handshake. When verification fails, it opens a second one that
does not verify, only to read the certificate. It answers `trusted: false` and the reason the
verification gave. A host that cannot be reached is `unavailable`, retryable.

### 4. The days left are counted by the connector, at the moment it read

`days_left` is the whole days from `read_at` to the expiry moment, rounded down. It is negative
after the moment has passed. Both moments stand in the output, so a reader can recompute it.

### 5. The requesting identity's credential goes to the RDAP server only

The contract has no connector without the requesting identity's credential (C-03). The credential
`EXPIRY_TOKEN` is sent as a bearer token to the configured RDAP server, which RFC 7481 permits.
A public RDAP server ignores it. A TLS handshake sends no credential.

## Alternatives

- **WHOIS.** Its answer is free text whose layout differs per registry. RDAP is its successor,
  and every generic top-level domain registry serves it.
- **The certificate transparency logs.** They list every certificate issued for a name, not the
  one a server presents now. A server can still present an old certificate.
- **A call that names any host.** A process could then make the connector reach any host on the
  network. The check connector refuses that for the same reason (ADR-0111).
- **The registry found by the IANA bootstrap file (RFC 9224).** It is how a client finds the
  RDAP server of any top-level domain. One configured server serves the business's own domains,
  which usually share one registry; bootstrap would add a download from IANA to every call.

## Consequences

- A new connector and its image `taktus-connector-expiry`, with a fake RDAP server and a fake
  TLS endpoint (`tests/fakes/expiry_service.py`), a scenario, and its rows in `CREDENTIALS.md`,
  the chart and the image workflow.
- B-1.09 is built: `blueprints/software-operations/processes/B-1.09-expiry.yaml`.

## Where this promise ends

- **Two of the things UC-03 B-1.09 names are read.** Keys, signing certificates, provisioning
  profiles and secrets have no open standard that publishes their expiry. They stay listed as
  not built in the blueprint's README.
- **Nothing is renewed.** Renewing a certificate needs control of the server: ACME (RFC 8555)
  runs where the certificate is served. Renewing a domain is a purchase and stays with a person
  (UC-03 B-1.09).
- **One RDAP server is configured.** A domain whose registry is another server is not answered;
  the connector does not follow the IANA bootstrap.
- **A certificate's chain is judged by the connector's trust store.** A server whose chain a
  browser trusts but the image's store does not is reported `trusted: false`. `--ca-file` adds
  the operator's own authority.
