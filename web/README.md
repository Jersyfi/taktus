# The web app

What a person sees of Taktus at work: the live representations of UC-6.10, drawn from the
records as they are now and moving when the work moves (ADR-0063).

## What it draws today

- **The run level** — where one run stands: each step with its method kind, exactness class and
  state, what a waiting step waits on, what each step used and what the run consumed so far,
  and all of it again as text. It follows the run's stream of changes and reads the level again
  on every change, without a reload.
- **The runs** the reader may see, as the tenant's stream says they stand, each leading to its
  run level. This is a way in, not the overview of UC-6.10.

Not yet: the process graph (#190), the overview (#191), the origin of a result (#192).

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
  motion from the first moment. It chooses no token and no colour of its own (ADR-0059).
- The reader gives an account key once per browser tab. It is kept in the tab's session storage
  and sent in `Authorization: Bearer`, never in an address.

| Path | What it is |
|---|---|
| `src/lib/types.ts` | the shapes the surface answers: a run level, a snapshot, a change |
| `src/lib/api.ts` | the surface's address, and a read with the key |
| `src/lib/stream.ts` | the stream of changes, read with `fetch`, resumed from its last position |
| `src/lib/live.ts` | the runs of the tenant's stream; a level followed live, read again on every change |
| `src/lib/shapes.ts`, `Glyph.svelte` | a glyph's tokens turned into a drawing, each token kept on it as an attribute |
| `src/lib/RunView.svelte` | the run level, and its text equivalent |
| `src/lib/motion.svelte.ts` | whether motion is allowed |
| `src/lib/key.ts`, `KeyForm.svelte` | the reader's key, for the tab's session |
| `src/lib/generated/fixtures.json` | written by `make generate`, never by hand: what the tests draw |
| `src/routes/` | the pages: the runs, and `#/runs/<id>` |

## Working on it

```sh
make gate-web          # packages from the lock file, types, tests, build — what CI runs
cd web && npm run dev  # a development server; point it at a running instance's surface
```

The tests are `src/**/*.test.ts`. They render the drawing and read back every token it drew
against the glyphs `reporting` drew (`tests/README.md`).
