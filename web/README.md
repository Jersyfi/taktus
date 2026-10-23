# The web app

What a person sees of Taktus at work: the live representations of UC-6.10, drawn from the
records as they are now and moving when the work moves (ADR-0063).

## What it draws today

- **The overview** — where the web app starts: the areas the reader may look into (today the
  tenant), the processes in each, how many of their runs work and wait right now, and the steps
  running now, each leading down to its process or run (ADR-0067).
- **The process level** — the steps of a process version as a graph, each with how it works and
  the runs it is running in right now, with the autonomy statement: the level the process runs
  at, and why. It lists the version's runs and every registered version (ADR-0064).
- **The run level** — where one run stands: each step with its method kind, exactness class and
  state, what a waiting step waits on, what each step used and what the run consumed so far,
  and all of it again as text. It follows the run's stream of changes and reads the level again
  on every change, without a reload.

- **The origin of a result** — the path from a step's result back through the steps and sources
  that produced it, from the provenance records, across runs; read once, since a record never
  changes (ADR-0068).

The run level also draws the decision requests a step raised, and links each result to its
origin.

- **A running step taken over** (UC-4.19, ADR-0128) — on the run level, a running worker step
  offers "take over", read back before it is asked. Once the runner served it, the page shows
  the state the step reached — goal, acceptance criteria, inputs, the worker's checkpoint and
  what it produced — and the lease's end, with how much of it has passed. The result is read
  back, as JSON or as the text written, before it is handed back. A take-over that lapsed, or an
  ask the runner refused because the step ended first, is said as such. No person is named.

- **What governs the work** (ADR-0122, DEC-0218) — the needs among the reports to the owner;
  each process's level, why it is there, and its correction rates per process and action; the
  instance's findings with their classification and their review, read back before it acts; and
  the tenants, for the holder of the administration key. The start page has one line per kind,
  saying how many are open or waiting, each leading to its page.
- **A report to the owner** — the page every link a channel carries to a report opens: what is
  needed, the steps, what stands still, by when, and how to answer. The reader answers there as
  in the channel; the reading comes back, and nothing is filed before the reader confirms it.
  The overview lists the open reports and alerts below it, newest first, each leading to its
  page (DEC-0218, ADR-0120).
- **What keeps the operation running** — the incidents, the alerts, the backup and the signals
  with the newest daily report, each a page of its own, and a line for each on the start page
  saying how many are open or red (ADR-0121). Each page is read once on opening.

## How it is built

- SvelteKit and TypeScript, built to static files (`npm run build` writes `build/`).
- The route is read from the address after `#`, and every reference in the build is relative, so
  that one build works under whatever path prefix an instance is served under.
  `scripts/relative.js` makes the page's own references relative after the build and fails the
  build if it finds none to rewrite.
- The image builds it in a stage of its own and carries only `build/`. The `api` role serves it at
  `{prefix}/app/`; the surface it reads is the directory above.
- It draws what a level hands it: every glyph comes from `reporting` with motion and without, and
  the app picks one by the reader's setting — the button *Stop motion*, or the system's reduced
  motion from the first moment. It chooses no token of its own (ADR-0059). It adds one colour per
  family on top of the form, paper and ink otherwise; every distinction is carried without it
  (M1.20, DEC-0185).
- The reader signs in with an account key once per browser (ADR-0119). The app sends it in
  `Authorization: Bearer` to `POST {prefix}/session`, once, and forgets it. The instance answers
  with a session cookie the page cannot read, which the browser sends with every request, in
  every tab, until it expires or the reader signs out. The key is never stored and never put in
  an address.

| Path | What it is |
|---|---|
| `src/lib/types.ts` | the shapes the surface answers: a run level, a snapshot, a change |
| `src/lib/api.ts` | the surface's address, and a read or a write as the signed-in reader |
| `src/lib/stream.ts` | the stream of changes, read with `fetch`, resumed from its last position |
| `src/lib/live.ts` | a level followed live, read again on every change |
| `src/lib/cells.ts`, `Glyph.svelte` | a glyph's tokens turned into a cell — membrane, nucleus, rings, cytoplasm, badge — each token kept on it as an attribute; a family's hue on top (M1.20) |
| `src/lib/Graph.svelte` | steps as a graph, placed by their dependencies |
| `src/lib/RunView.svelte` | the run level, and its text equivalent |
| `src/lib/takeover.ts`, `TakeoverPanel.svelte` | a running step taken over: the steps that offer it, where an ask stands, the state, the lease, the result read back before it is handed back (ADR-0128); the reader's own ask is held while the page is open, and stored nowhere |
| `src/lib/OverviewView.svelte` | the overview, and its text equivalent |
| `src/lib/OriginView.svelte` | the origin of a result, and its text equivalent |
| `src/lib/ProcessView.svelte` | the process level, its autonomy statement, its runs and versions, and its text equivalent |
| `src/lib/links.ts` | where each level lives in the web app |
| `src/lib/motion.svelte.ts` | whether motion is allowed |
| `src/lib/session.ts`, `SignInForm.svelte` | signing in with the key, once, and signing out |
| `src/lib/generated/fixtures.json` | written by `make generate`, never by hand: what the tests draw |
| `src/routes/` | the pages: the overview at `#/`, `#/runs/<id>`, `#/processes/<id>` with an optional `/<version>`, `#/origins/<run>/<step>`, and `#/requests` with an optional `/<id>`: the decision requests addressed to the reader, answered and confirmed there (ADR-0063 §4), and `#/changes/<process>`, where a process is changed in dialogue and rolled back (ADR-0091 §6) |
| `src/lib/RequestView.svelte` | one decision request: what happened, the options with the recommended one, what is blocked, by when; an answer by option or in the reader's words, and the reading confirmed before anything takes effect |
| `src/lib/ChangeView.svelte` | a process changed in dialogue: the request in words, each open proposal as its difference in words, its rehearsal with the result read from the rehearsal's run (offered when there is none, shown as a rehearsal in which nothing left the system), commissioning offered once that run has finished, and discarding, and a rollback for every earlier version |
| `src/lib/governance.ts`, `GovernanceLines.svelte` | the shapes of what governs the work, its reads and answers, the start page's line per kind, and the administration key for the tab's session (ADR-0122) |
| `src/lib/NeedsView.svelte`, `#/needs` | the needs among `GET /owner/reports`: what is needed, the steps, what stands still, by when, the state and the answer filed; each need leads to its report's page, where it is answered (ADR-0120) |
| `src/lib/AutonomyView.svelte`, `#/autonomy` | `GET /autonomy`: each process's level in force, the stated one and why, the incident that lowered it, and each unit's rates over 7 and 28 days against the tenant's limit |
| `src/lib/FindingsView.svelte`, `#/findings` | `GET /findings`: each lack with its classification and the text it would leave in; at the level `review`, send, not now or local for us, read back and confirmed |
| `src/lib/TenantsView.svelte`, `#/tenants` | the tenants under the administration key: listed, created and renamed, each said back first |
| `src/lib/reports.ts`, `ReportPage.svelte`, `#/reports/<id>` | a report to the owner: its view as `GET /owner/reports/{id}` sends it, the answers it offers, an answer sent to `POST …/answer` and the reading confirmed at `…/confirm` (ADR-0120) |
| `src/lib/OpenReports.svelte` | the overview's list of the reports that wait for an answer, newest first, read from `GET /owner/reports` |
| `src/lib/YoursView.svelte`, `#/me` | the reader's own page: how long runs waited on their own decisions, each with its time, their median, and beside it their role and department only aggregated — `GET /decisions/response-times`, computed for its reader alone (ADR-0015) |
| `src/lib/operation.ts`, `OperationPage.svelte` | what keeps the operation running (ADR-0121): the shapes `GET /operation`, `/incidents`, `/alerts`, `/backup`, `/signals` and `/signals/daily-report` answer, where each page lives, the sentence each opens with, and their common frame |
| `src/lib/IncidentsView.svelte`, `#/incidents` | the incidents, open ones first: what was expected, what happened since, the process version and every run each names (ADR-0107) |
| `src/lib/AlertsView.svelte`, `#/alerts` | the alerts in effect first, what became of each report, and the runs, steps and process versions each is about (ADR-0106) |
| `src/lib/BackupView.svelte`, `#/backup` | the backup's last success, its newest failure and by when the next success is due (ADR-0106) |
| `src/lib/SignalsView.svelte`, `#/signals` | every signal judged against its corridor, red first, each with the run that measured it and its case, and the newest daily report (ADR-0109) |
| `src/lib/OperationSection.svelte`, `OperationLines.svelte` | the start page's section: its own sentence of what needs a look, then one line per kind leading to its page |

## Working on it

```sh
make gate-web          # packages from the lock file, types, tests, build — what CI runs
cd web && npm run dev  # a development server; point it at a running instance's surface
```

The tests are `src/**/*.test.ts`. They render the drawing and read back every token it drew
against the glyphs `reporting` drew (`tests/README.md`).
