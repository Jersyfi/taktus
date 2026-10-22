# ADR-0122 — The web app shows what governs the work, and a review acts only on what was read back

**Status:** accepted · extends ADR-0063 (the web app reads the surface), ADR-0110 (corrections and levels), ADR-0118 (findings and their review) and ADR-0104 (tenants) · serves DEC-0218 · issue #563

## Context

DEC-0218 makes the web app the place where everything Taktus holds is found, for the reader's
role. What decides how far Taktus may act had no page. Four kinds were missing.

- **Needs.** A need is a report to the owner of kind `need` (ADR-0028, ADR-0045).
  `GET /owner/reports` already answers every report, for the owner and whom the owner named.
- **Levels and corrections.** `taktusctl corrections list` printed each unit's correction rate
  (ADR-0110 §3). The surface had no route for it.
- **Findings.** `taktusctl findings` and `taktusctl findings review` showed and reviewed them
  (ADR-0118 §4). The surface had only the intake of other instances.
- **Tenants.** `GET`, `POST` and `PATCH /administration/tenants` existed, under the
  administration key (ADR-0104 §4).

Three questions had to be answered. Which routes are new, and who reads them? How does a review
in a browser read the answer back before it acts (ADR-0008)? How does the start page say what
waits?

## Decision

### 1. Two read routes and two answer routes are new

- `GET /autonomy` answers, for every process the reader may see, the level its active version
  states and why, the level a rule lowered it to and the incident that says why, and the level
  in force. With each unit's correction rate over 7 and 28 days, the raises proposed since the
  unit's last change of level, and the tenant's limits
  (`adapters/driving/rest/autonomy.py`).
- `GET /findings` answers every product finding of the instance, what the rule made of it, how
  often it was met, how long it held runs up, and exactly the text it would leave in
  (`adapters/driving/rest/review.py`).
- `POST /findings/{lack}/review` and `POST /findings/{lack}/review/confirm` are the review.

Needs are read from `GET /owner/reports`, and the tenants from the existing routes. No route is
added for either.

### 2. Who reads what

- `GET /autonomy` admits any account key. A process is shown only where the visibility
  predicate of the live representation admits it (ADR-0055 §5). Every figure is counted per
  process and action class. The ledger entries the rule reads carry no actor (ADR-0110 §2), so
  no figure can name the person who released, corrected or rejected (principle 14, ADR-0015).
- `GET /findings` and the review admit the owner and the people the owner named, as the reports
  do (`ReportQueries.may_read`). Anyone else is answered `403`.
- The tenants admit the administration key only. The web app asks for it on the tenants page
  and keeps it for the tab's session, apart from the account key.

### 3. A review is read back, and the confirmation carries what was read back

An answer in review — `send`, `not` or `local` — is sent to `POST /findings/{lack}/review`.
Nothing is done. The answer comes back in words, with the exact text that would leave, and a
`confirmation`: a SHA-256 digest of the reader's identity, the lack, the answer and that text.

`POST /findings/{lack}/review/confirm` takes the answer, the `confirmation` and `confirmed`.
Rejected, nothing is done. Confirmed, the surface computes the digest again from the finding as
it is now. Where it differs, the answer is refused with `409`, and nothing is done. A text that
changed since it was read back is therefore never sent on an older yes. A confirmation by
another person, or of another answer, differs too. Only then does `send` call `send_one`,
`local` call `call_local`, and `not` do nothing, as `taktusctl findings review` does.

The reading is not stored. The digest is the reading's whole state, and the second request
proves it holds.

### 4. The start page has one line per kind

The start page reads `GET /decisions`, `GET /owner/reports`, `GET /autonomy`, `GET /findings`
and, where the tab holds the administration key, `GET /administration/tenants`. It shows one
line per kind: how many decision requests wait, how many needs are open, how many processes run
below their stated level and how many raises wait, how many lacks wait for a review, and how
many tenants the instance serves. Each line leads to its page. A kind the surface refuses the
reader has no line.

### 5. Every page draws the surface's own answer

`make generate` writes each answer the pages draw into `web/src/lib/generated/fixtures.json`,
with the surface's own functions over example facts. The web app's tests render those. A change
of a route's shape changes the fixture, and a test of the page fails where it no longer fits.

## Alternatives

- **A route for needs.** `GET /owner/reports` holds them already. A second route would be a
  second answer to the same question.
- **Store the reading of a review, as a decision request does.** A decision request is a record
  with a lifecycle (ADR-0042). A finding in review is not one. A stored reading would need a
  table, a lifetime and a cleanup, for what one digest proves.
- **Act on the first request, with a browser dialog to confirm.** The dialog lives in the page,
  and a request without the page would act unread. ADR-0008 asks for the reading on the
  surface's side.
- **Show correction rates only to the owner.** A process's level is how far Taktus may act in
  it. A reader who may see the process may see why it runs at that level (principle 7). The
  rates carry no person, so nothing of a person is shown.

## Consequences

- `adapters/driving/rest/autonomy.py` and `review.py`. `RestServices` gains `corrections` and
  `findings`. `tenants.tenant_document` is the tenant's shape, public for the fixtures.
- `api/openapi.yaml` gains `/autonomy`, `/findings`, `/findings/{lack}/review` and
  `/findings/{lack}/review/confirm`.
- The web app gains `#/needs`, `#/autonomy`, `#/findings` and `#/tenants`, and a section of the
  start page (`GovernanceLines.svelte`, `governance.ts`).
- `tools/generate.py` writes the fixtures `governance`.

## Where this promise ends

`GET /autonomy` reads the tenant's correction entries once per request, as `taktusctl
corrections list` does, and reads each visible process's level one by one. A tenant with many
processes pays that on every opening (#522). A process without an active version is not shown.
A lowering of a version other than the active one is not shown.

Who may see a process is the tenant boundary until role-based views exist (UC-6.4). Every reader
of the tenant sees every process's rates until then.

The review admits whom the owner named. Rights per role do not exist (UC-7.3). A confirmation
whose digest matches is acted on. Two people who each read the same answer back may each confirm
it. `send_one` sends only what the other side has not been given, so the second sends nothing.

The tenants page sends the administration key from the browser. It is as safe as the tab it is
typed into. The key is kept in the tab's session storage, never in an address, and never sent
anywhere but this instance.

Needs are shown, not answered, here. An answer to a report in the web app is #561's.
