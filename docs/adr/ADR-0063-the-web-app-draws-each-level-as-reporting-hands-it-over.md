# ADR-0063 — The web app is a static build in the image, and draws each level as `reporting` hands it over

**Status:** accepted · builds the web app and the run level of UC-6.10 (issue #105, DEC-0055);
answers the question ADR-0059 left to this change

## Context
UC-6.10 requires four live representations — the overview, the process, the run and the origin
of a result — and leaves the technology to the change that builds the web app (§3). Issue #105
builds the web app and the first of the four, the run level. Five questions are open.

1. How the web app is built and served, given that an instance chooses its path prefix when it
   starts (`TAKTUS_PATH_PREFIX`), not when the image is built.
2. How the visual vocabulary reaches the web app (ADR-0059 §1 leaves it to this change).
3. Where a level is composed: in the web app from several reads, or on the surface from the
   records.
4. How a level stays live (ADR-0055 says the web app subscribes before it draws).
5. How the reader proves who they are. The surface authenticates with an account key in the
   `Authorization` header and nowhere else (ADR-0040, ADR-0055 §1); there is no sign-in flow yet
   (UC-7.3).

Facts that bound the answer:

- **Reporting owns every view and no figure** (ADR-0029). It never imports another component
  (ADR-0003); the composition root hands it the records.
- **The web stack is named**: SvelteKit, embedded into the image (`README.md`, technology table;
  `docs/architecture/project-structure.md`). TypeScript is the web app's language (CLAUDE.md §7).
- **The image is the deployable**, one for every role (ADR-0002). The web app is not a tier-1
  dependency of the integration-code rules (`docs/architecture/contracts.md` §7): Taktus runs
  without it, as the `api` role's own row says — "the interface is down, runs continue".

## Decision

### 1. A static build, served by the `api` role under `{prefix}/app/`
The web app under `web/` is built to static files. The image builds it in a stage of its own,
from the lock file, and carries only the result; the runtime image holds no Node. The `api` role
serves the build at `{prefix}/app/` when the image holds it, and `{prefix}/app` is redirected
there by a relative location.

The prefix is not known when the app is built. The router therefore reads the route from the
part of the address after `#`, and every reference in the build is relative to the page. The
surface the app talks to is the directory above its own. One build serves every prefix.

### 2. A level is a request on the surface, drawn by `reporting`
Each level is one read: `GET /levels/runs/{run_id}` for the run level, and one more per level as
it is built (#190, #191, #192). `reporting` composes it from the records of the component that
owns them, read through a port that the composition root binds; it stores nothing.

A level carries every fact the representation shows and, for every element, **its glyph twice**:
with motion allowed (`drawn.moving`) and without (`drawn.still`), both computed by the
vocabulary (ADR-0059 §3). It carries the element's text equivalent as well. A figure is the
owning component's own value, flattened into named numbers and never computed again.

This answers ADR-0059's open question: **the vocabulary reaches the web app inside every level**,
as the glyphs `reporting` computed. The web app picks one of the two glyphs by the reader's
setting and turns its tokens into pixels; it computes no token. The vocabulary is also served
whole, `GET /vocabulary`, for a key to the shapes; it says nothing about any tenant and needs no
account key.

The web app's tests hold its drawing to the glyphs. `make generate` writes a run level drawn by
`reporting` from example facts — every method kind, every exactness class, every motion — beside
the vocabulary, into `web/src/lib/generated/fixtures.json`; a Python test fails a stale copy. The
web app renders that level and reads back every token it drew from the drawing's attributes. A
token other than the one handed over fails, and so does a token of the vocabulary the web app
has no drawing for.

### 3. Live: the scope's stream, and the level read again
The web app opens the stream for the level's scope (`GET /changes?run=…`) before it draws. Its
first event, the snapshot, triggers the first read of the level. Every change triggers one more.
Reads are coalesced: while one is under way, any number of changes asks for exactly one more.
The level is never assembled from the stream itself; the stream says that something changed,
and the level is read again from the component that owns it (ADR-0055 §4).

### 4. The reader's key, for the tab's session
The reader gives an account key. The web app keeps it in the browser tab's session storage, so
that it ends with the tab, and sends it in `Authorization: Bearer` only. It never puts the key in
an address. A `401` asks for the key again.

A level the reader may not see is answered `404`, exactly as one that does not exist, by the one
predicate of `reporting` that the stream asks too (ADR-0055 §5).

### 5. The web app's checks are a gate
`make gate-web` installs the web app's packages from its lock file, checks its types, runs its
tests and builds it. CI runs it in a job of its own, which may not skip. `make gates` runs it
too; without Node on the path it skips and says so, as the database tests do without Docker.

## Alternatives
- **The web app computes glyphs from the vocabulary document.** It would hold a second
  implementation of `drawing.py` in TypeScript. ADR-0059 §1 says a representation chooses no
  token; a second implementation chooses them all, and the check could only test it through a
  copy of the facts.
- **The web app composes a level from `GET /runs/{id}` and the stream.** The run's whole record
  would reach the browser, including what no level shows, and the figure's definition would be
  repeated in the browser (ADR-0029: one definition).
- **A server-rendered web app** — SvelteKit's own server, or pages rendered by the `api` role.
  The first is a Node process in the image beside Python (CLAUDE.md §7 keeps one server-side
  language); the second couples every view to Python templates and loses the stream-driven
  redraw.
- **Routes by path, with the prefix fixed when the image is built.** One image per prefix, or a
  rewrite of the build at start. An instance moved under another prefix would need a rebuild.
- **The key in local storage, kept across visits.** Less typing. A key that outlives the tab is
  readable by anything that later runs on that origin; the tab's session is the shorter exposure.
- **The vocabulary as a file generated into the web app and read at run time.** ADR-0059 allows
  it. With the glyphs in each level it would be read only for a legend, and a copy can be stale;
  the request cannot.

## Consequences
- The image gains a build stage with Node; its runtime stage gains the static build and nothing
  else. `.dockerignore` keeps every `node_modules` out of the context.
- The surface gains `GET /levels/runs/{run_id}` and `GET /vocabulary`, and serves `/app/`.
- `reporting` gains the run level (`domain/model/levels.py`, `domain/service/levels.py`), its
  port (`ports/levels.py`) and its query (`application/query/levels.py`); the composition root
  binds the port to the run's repository (`composition/levels.py`).
- `make generate` writes the web app's fixtures beside `api/openapi.yaml`.
- CI gains the job `web`, and `make gates` the target `gate-web`.
- Each further level of UC-6.10 is one more request of the same shape and one more page.

## Where this promise ends
The web app draws what a level hands it and cannot know whether the level is current; that the
stream delivers within 5 seconds is ADR-0055's, and a read of the level after a change adds one
request to it. The check holds the drawing's attributes to the tokens; whether the pixels look
as the tokens say is seen by a person, not by a test (ADR-0059). Session storage keeps the key
from other tabs and later visits, not from a script running in the same tab; the web app loads
nothing from another origin, and nothing here defends a browser that is already compromised.
A reader whose browser refuses session storage gives the key again on every load. The web app
works under any prefix only because every reference is relative; a proxy that rewrites the
page's addresses breaks it, and that is the operator's configuration. Until UC-6.4 the
predicate is the tenant boundary, so any identity of a tenant sees every run of it. The export
of UC-5.7 does not exist yet; a level's figures are held equal to the run's own record as the
read API gives it, and to the export once it exists. A sign-in flow is not decided here.
