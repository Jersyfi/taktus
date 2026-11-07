# ADR-0234 — The security check of a web application is passive

**Status:** accepted · extends ADR-0218 · UC-03 B-7.09, DEC-0228

## Context

UC-03 B-7.09 asks for a penetration test of the business's own web application, from a fresh
context without the source, as an outside attacker would: reading other users' data as a test
user, counting up identifiers, calling admin routes. ADR-0218 built the browser worker it
needs and bounded what such a test finds to what its checks ask for.

A test that acts on the application — that submits, guesses or reads what it should not — can
change data and trip the application's own defences. What it may try is decided per
application by whoever answers for it. A check that only reads what any visitor receives
changes nothing and needs no such decision.

## Decision

### 1. A check of the browser worker may be a passive security check

A check that names `security: true`, or a task whose inputs name it for every check, reports
beside what the page shows:

- whether the page was served over TLS, and the TLS protocol;
- which protecting response headers are missing: `strict-transport-security` (over TLS only),
  `content-security-policy`, `x-content-type-options`, `referrer-policy`, and
  `x-frame-options` unless the policy names `frame-ancestors`;
- which headers name the server's software: `x-powered-by`, `x-aspnet-version`,
  `x-aspnetmvc-version`, and `server` where it carries a version;
- which cookies lack `Secure` or `HttpOnly`, by name;
- which paths of a fixed list answer with the content their name promises: a repository's
  `HEAD` and `config`, an environment file, a version-control entries file, a password file,
  cloud credentials, a private key, a server status page, a PHP information page, a folder
  index of a desktop. Each is one GET of a path a visitor could type; a path counts as exposed
  only when it answers 200 and its content matches the path's signature.

Every finding makes the check not pass. No header's value, no cookie's value and nothing an
exposed path holds enters the report.

### 2. B-7.09 is the passive half

The bundle B-7.09 runs the worker on the pages given, within the frame's allowed hosts, and
files a page with a finding as an issue once, at level 2. The active half — test users reading
each other's data, identifiers counted up, admin routes called — is not built: it waits for a
person's decision per application on what may be tried, and for test users the application
holds.

## Alternatives

- **The baseline scan of an application security scanner.** Its passive mode reads the same
  headers and cookies, but it also spiders the application, following every link it finds:
  more requests than a visitor sends, and an image of its own to keep. The browser worker
  already holds the frame inside the browser.
- **The active half now.** It acts on the application without the decision of the person who
  answers for it.

## Consequences

- `workers/browser/browse.py`: the security section of a report; `worker.py`: `security` in a
  task's inputs.
- `blueprints/software-operations/processes/B-7.09-security-check.yaml`.
- `tests/workers/test_browser_worker.py`, `tests/composition/test_software_operations_remainders.py`.

## Where this promise ends

- It finds what a visitor's browser receives. A weakness behind a sign-in, an injection, an
  access control that fails for another user: none is found.
- The fixed list is ten paths. A file exposed under another name is not found.
- A header that is present is not judged on its value: a content security policy that allows
  everything passes.
- An issue names a weakness. Where the repository service's issues are public, a person must
  not confirm the filing; the bundle files at level 2 for that reason.
