# NTC-0138 — The web app's tests, and their gate

**Mode entry:** M2.2
**Kind:** test-strategy
**Decided:** 2026-10-10
**Raised in:** issue [#105](https://github.com/Jersyfi/taktus/issues/105), in the pull request that closes it

## 1. What was decided

The web app is tested with its own runner, beside its code, and held to the vocabulary through
glyphs that `reporting` drew:

- `make gate-web` installs the web app's packages from its lock file, checks its types, runs its
  tests and builds it. CI runs it in the job `web`, under `TAKTUS_REQUIRE_NODE`, where it may not
  skip. `make gates` runs it too; without Node on the path it skips and says so, as the database
  tests do without Docker. `make doctor` says what Node is for.
- `make generate` writes `web/src/lib/generated/fixtures.json`: the vocabulary, and a run level
  `reporting` drew from example facts that use every method kind, every exactness class and every
  motion. A Python test fails a stale copy, as `tests/adapters/rest/test_openapi.py` does for
  `api/openapi.yaml`.
- The web app's tests render its drawing and read back every token from the drawing's attributes.
  A token other than the one handed over fails, and so does a vocabulary token with no drawing.
  This is ADR-0059's check on the web app's side: the Python check holds the tokens a level hands
  over, this one holds what the web app drew from them.
- The live path is tested in the web app with a stream and a surface the test answers: the key in
  the header and never in the address, the resume from the last position, a level read again on
  every change and coalesced, a `404` shown as absent. That a change reaches the stream within 5
  seconds stays `tests/integration/test_live_changes.py`'s.

## 2. The evidence

- `web/src/lib/drawing.test.ts`, `web/src/lib/stream.test.ts`, `web/src/lib/live.test.ts`; 15
  tests, green in about a quarter of a second; `make gate-web` about 5 seconds with the packages
  cached.
- `tests/components/reporting/test_run_level.py::test_the_web_apps_fixtures_are_what_make_generate_writes`.
- `tests/README.md` says the same.

## 3. What was considered

- **Run the web app's tests in a browser.** Rejected for now: the drawing's tokens are read from
  its markup without one, and a browser in CI adds minutes and a dependency for what the markup
  already shows. Whether the pixels match the tokens is a person's look (ADR-0059, *Where this
  promise ends*).
- **Keep the web app out of `make gates`.** Rejected: `make gates` is everything CI runs, and the
  skip without Node keeps it runnable where Node is absent.
- **Copy the vocabulary into the web app by hand.** Rejected: a copy drifts; a generated file is
  held to its source by a test.

## 4. Which entry permits it

M2.2, *"A change of test strategy and what the tests now cover."* No gate is weakened: a new one
is added, and it cannot skip in CI.
