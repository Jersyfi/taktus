# ADR-0120 — Every link to a report opens its page in the web app, and the report is answered there

**Status:** accepted · builds issue #561 on DEC-0218 and UC-6.11 · amends ADR-0045 (the link a
message carries) and ADR-0063 §4 (the writes the web app makes)

## Context
On 2026-10-22 the owner opened the link of an alert. The link led to `/owner/reports/<id>`, a
route of the HTTP surface. The surface answers a request without an account key with `401` and a
problem document. The owner was signed in to the web app, but the web app keeps its key in the
browser tab and sends it only in a header (ADR-0063 §4). A link opened from a chat carries no
header. So the owner saw a JSON error instead of the report.

DEC-0218 decided that the web app is where everything Taktus knows is found. Every link a channel
carries opens a page of the web app under the reader's sign-in. UC-6.11 §2 requires it.

Three questions were open:

1. Where the link leads, given that the instance chooses its path prefix when it starts.
2. How an old link, already in a chat, keeps working.
3. How the reader answers on the page. ADR-0063 §4 allows the web app two writes only: the answer
   to a decision request and its confirmation. A need, a date, a failure and the daily signals
   are answered in the channel alone.

## Decision

### 1. The link is the report's page
`rendering.view_url` builds `{view_base}/app/#/reports/{id}`, the identifier escaped. The route
is the part after `#`, as for every other page of the web app (ADR-0063 §1). `web/src/lib/links.ts`
builds the same route with `reportLink`. A message without a configured `view_base` carries no
link, as before.

### 2. The page reads the report with the tab's key
The route `#/reports/<id>` reads `GET /owner/reports/{id}` with the key of the tab. A tab without
a key shows the web app's sign-in form first, and then the report. A refused key asks again. The
page shows what the message showed: the title, what is needed, the steps, what stands still, by
when, the links and the answers offered. Its look is the session's (DEC-0185): a sentence of
state under the title, then the four items, then how to answer.

### 3. The start page lists the open reports
The start page reads `GET /owner/reports` and lists the reports that are not filed, newest
first. Each item leads to its page. A line above the list says how many wait. A reader who may
not read the reports gets `403`, and the section is not shown.

The needs page (ADR-0122) shows the needs among the reports. Each need there leads to its
report's page, where it is answered.

### 4. An old link sends a browser to the page
`GET /owner/reports/{id}` from a browser is redirected to the page with `303 See Other`. The
request counts as a browser's when its `Accept` header names `text/html` and it carries no
`Authorization` header. The location is relative, `../../app/#/reports/{id}`, so that it is right
under every prefix. Any other request is answered as before: the view, or a problem document.

### 5. A report is answered on its page by the channel's rules
Two routes are added: `POST /owner/reports/{id}/answer` and `POST /owner/reports/{id}/confirm`.
They are served by the same use case as an answer in the channel, `AnswerInChannelHandler`, with
the command `AnswerOnPage`. The rules are the channel's:

- only the owner and the people the owner named answer; anyone else is not filed;
- an answer is an offered answer chosen by its identifier, or the reader's words read by the
  channel's rule; a decision request's answer is read by the decision component;
- the reading comes back in the sentence the channel would have said, in the owner's language;
- only the same person's confirmation files the answer; a rejection opens the report again.

The page is not a thread: nothing is said in the channel. The filed answer names `web` as where
it was given. A confirmation with no reading of this person waiting is answered `409`.

This amends ADR-0063 §4: the web app now makes four writes. It still decides nothing itself.

## Alternatives
- **Keep the link on the surface and let it render HTML.** The surface would then serve pages
  beside JSON, and a page would need a sign-in of its own. ADR-0063 rejected server-rendered
  pages.
- **Put the key into the link.** A key in an address ends up in the chat, in browser history and
  in proxy logs (ADR-0055 §1).
- **Answer a non-decision report on the page through `/decisions`.** Those routes know only
  decision requests. A need, a date, a failure and the daily signals would stay unanswerable on
  the page.
- **A second answer use case for the page.** Its rules would drift from the channel's. One use
  case with two places keeps one reading of an answer.

## Consequences
- `rendering.view_url` points at the web app. Every message of every kind links the page.
- `AnswerOnPage`, `AnswerInChannelHandler.on_page`, and `Answer.said` in
  `reporting/application/service/answer_in_channel.py`. The channel's own path is unchanged.
- `RestServices.answer_report`, the two routes and the redirect in
  `adapters/driving/rest/app.py`; `api/openapi.yaml` regenerated.
- In the web app: `reports.ts`, `ReportPage.svelte`, `OpenReports.svelte` and the route
  `routes/reports/[id]`.

## Where this promise ends
The link opens the page only where the operator configured the channel's `view_base`. An
instance served without the web app's build answers the redirected browser with `404` at
`{prefix}/app/`.

The sign-in lasts as long as the tab (ADR-0063 §4). A link opened in a new tab asks for the key
again. A sign-in that outlasts the tab is its own issue.

A browser is recognised by its `Accept` header. A client that sends `text/html` without a key is
redirected too, and must send `Accept: application/json` to get the problem document.

Only reports have a page. Links to other records — incidents, signals, backups, findings — are
their own issues (DEC-0218). The start page lists open reports for their readers only: the owner
and the people the owner named. Another reader sees no list, not an empty one.

An answer on the page is filed exactly as in the channel, but the channel does not hear of it. A
person who reads only the channel sees the report as answered only in the view and in the
repository text.
