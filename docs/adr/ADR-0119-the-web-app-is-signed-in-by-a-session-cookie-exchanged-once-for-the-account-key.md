# ADR-0119 — The web app is signed in by a session cookie, exchanged once for the account key

**Status:** accepted · amends ADR-0063 §4: the reader's key is no longer kept for the tab; amends ADR-0055 §1: the stream accepts the session cookie beside the key · extends ADR-0040 and ADR-0020 · issue #564, DEC-0218

## Context

ADR-0063 §4 kept the reader's account key in the browser tab's session storage. The key ended
with the tab. Every link opened in a new tab therefore asked for the key again. DEC-0218 makes
the web app the place where everything Taktus knows is found, and every link a channel carries
opens a page of it. A sign-in that does not reach the next tab defeats that.

Three facts bound the answer.

- **The account key proves an identity on the surface, in `Authorization: Bearer` and nowhere
  else** (ADR-0040, ADR-0055 §1). Only its digest is kept (`identity.key_digest`).
- **Every table carries its tenant and row-level security** (ADR-0020).
- **The web app is a static build served by the `api` role under `{prefix}/app/`** (ADR-0063
  §1). Its page and the surface are one origin.

A key kept by the page for longer than a tab is readable by any script that later runs on that
origin. ADR-0063 rejected local storage for exactly that reason. A longer sign-in must therefore
be held where no script can read it.

## Decision

### 1. The key is exchanged once
`POST {prefix}/session` takes the account key in `Authorization: Bearer`. When the key proves an
identity, the instance creates a **session** and answers `201`. The body names the tenant, the
identity and when the session expires. The session's token is in the cookie only, never in the
body. A key that proves nothing is answered `401`, and no cookie is set.

The web app sends the key in this one request and then forgets it. It keeps the key in no
storage and puts it in no address.

### 2. The cookie
The answer sets the cookie `taktus_session` with these attributes:

- `HttpOnly`: no script of the page can read it.
- `Secure`: the browser sends it over HTTPS only. Most browsers also send it to a plain-HTTP
  `localhost`, for a local installation.
- `SameSite=Strict`: the browser does not send it with a request that another site starts.
- `Path={prefix}/`: it reaches this instance's surface and nothing else on the host.
- `Max-Age`: the session's lifetime. No `Domain`: this host only.

The lifetime is `TAKTUS_SESSION_HOURS`, 12 hours by default, at least 1 and at most 720. A
session lasts from its sign-in; using it does not extend it.

The cookie carries no `__Host-` prefix. That prefix requires `Path=/`, and an instance under a
path prefix scopes its cookie to the prefix.

### 3. Accepted wherever the key is
The surface accepts the cookie on every route that accepts the account key, the stream of
changes included (ADR-0055). A middleware of the HTTP adapter hands the cookie to the routes as
the request's credential before any route reads it. The routes then ask the identity component,
which answers with the same identity a key would.

A request that carries its own `Authorization` header is left as it is. The bearer key keeps
working for every other client: the command line, a script, another service. The cookie is then
not read. A token is accepted from the cookie and nowhere else: not in a header a client writes,
not in an address.

The administration of tenants is not reached with a cookie. It admits the instance's
administration key only (ADR-0104 §4).

### 4. When a session ends
A session proves its identity while all three hold:

1. its time is not up;
2. the person has not signed out;
3. the identity still holds the key the session was exchanged for.

`DELETE {prefix}/session` ends the session now and clears the cookie. A new key for the identity
(`taktusctl identity key`) ends every session exchanged for the old one. The session records the
digest of the key it was exchanged for, and a session whose digest is not the identity's is
refused. A stream of changes that is open when its session ends ends too: the stream asks again
before every batch and every heartbeat (ADR-0055 §5).

### 5. A request from another site is refused
A request that changes state, authenticated by the cookie, must come from the instance's own
pages. `SameSite=Strict` is the first guard. The second is the request's own statement of where
it comes from:

- where the browser sends `Sec-Fetch-Site`, it must be `same-origin`;
- otherwise, `Origin` must name the host the request was sent to (`Host`, or the first
  `X-Forwarded-Host`).

A request with neither is refused with `403`. `GET`, `HEAD` and `OPTIONS` change no state and
are not checked. A request authenticated by the bearer key needs neither statement: another site
cannot make a browser send a header it chose without the instance's consent, and the instance
grants no such consent.

### 6. What is kept
A session is a row of the table `browser_session`, with its tenant and row-level security
(ADR-0020, migration 0063). The row is kept under a digest of the token. The token itself is
kept nowhere. The row names the identity, the digest of the key, when the session began, when it
expires and when it was ended.

A sign-in and a sign-out write no ledger entry. When a person uses the web app is not a
measure of anybody, and no figure reads the table (principle 14). Neither the key nor the token
is ever written to a log.

### 7. The web app
The web app asks for the key only when the surface answers `401`. A link opened in a new tab is
read at once with the cookie. The bar of every page carries *Sign out*. On loading, the web app
removes a key an earlier version left in the tab's storage.

The instance's administration key is not an account key and is not exchanged. The tenants page
keeps asking for it and holds it for the tab, as ADR-0122 decides. It travels in
`Authorization: Bearer`, so the surface reads no cookie on those requests (§3).

## Alternatives

- **The key in local storage, kept across visits.** ADR-0063 rejected it, and the reason holds:
  any script that runs on the origin later reads it, for as long as the key is valid.
- **A token in local storage, sent as a bearer header.** The token is shorter-lived than the
  key, but it is still readable by any script on the origin. An `HttpOnly` cookie is not.
- **The key itself as the cookie.** A cookie stays in the browser's store until it expires.
  The key does not expire, and replacing it would be the only way to end a sign-in.
- **A signed cookie without a table.** No lookup per request, but a signed cookie cannot be
  ended before its time: neither sign-out nor a new key would end it.
- **A synchroniser token against cross-site requests, instead of the origin check.** The web
  app would read a second token and send it with every write. `SameSite=Strict` and the browser's
  own statement of the origin protect the same writes without a second secret on the page.
- **Single sign-on with an outside provider.** Not this change (issue #564); a later use case.

## Consequences

- The surface gains `POST /session` and `DELETE /session` (`adapters/driving/rest/session.py`),
  and the middleware `SessionCookies` in front of every route of the `api` role.
- The identity component gains the aggregate `BrowserSession` and `sign_in`, `session` and
  `sign_out` on `IdentityDirectory`. `issue_key` ends every session of the old key by
  replacing the digest the sessions are compared with.
- PostgreSQL gains the table `browser_session` (migration 0063). The application role may read,
  insert and update it.
- The setting `TAKTUS_SESSION_HOURS` is added. No new secret parameter is added: the token is
  made by the instance and is never configured.
- The web app's `key.ts` and `KeyForm.svelte` are replaced by `session.ts` and
  `SignInForm.svelte`. Its reads, writes and stream send the cookie and no key.

## Where this promise ends
The cookie is out of reach of the page's scripts, not of a person or a program that controls
the browser. A compromised browser, an extension with access to the site, or someone at the
unlocked device can use the session until it ends. Signing out ends the session in that browser
only. A person who lost a device ends its session by having the key replaced.

`Secure` holds only over HTTPS. An instance served over plain HTTP to any host but `localhost`
does not receive the cookie back, and the web app asks for the key on every page. Not every
browser keeps a `Secure` cookie for plain-HTTP `localhost` either. Serving over HTTPS is the
operator's.

The origin check trusts the browser's `Sec-Fetch-Site` and `Origin`. A client that is no browser
can write either header, but such a client must already hold the token, and then it holds the
session. A proxy that rewrites `Host` without setting `X-Forwarded-Host` makes every write from
the web app fail with `403`; that is the operator's configuration.

`SameSite=Strict` withholds the cookie from the navigation that opens the instance from another
site. The page loads all the same, because it needs no cookie. Its first read is the page's own,
and carries the cookie.

A row is kept after its session ends, as a link code is. Removing old rows is not part of this
decision. The lifetime bounds a session that is never ended; it does not bound how long the key
it was exchanged for is valid.
