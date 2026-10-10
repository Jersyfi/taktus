# NTC-0139 — The `api` role serves the process level

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-10
**Raised in:** issue [#190](https://github.com/Jersyfi/taktus/issues/190), in the pull request that closes it

## 1. What was decided

The second of UC-6.10's four levels, the process, is built as ADR-0064 decides. What the
software does differently:

- The `api` role serves `GET /levels/processes/{process_id}`, with an account key: the steps of
  the active version — or of the version `?version=` names — as a graph, each with its method
  kind, exactness class, why that method, what was not chosen, where it falls back, which steps it
  follows, and the runs it is running in right now; the autonomy statement as stated and in words;
  every registered version and which is active; the runs of the version the reader may see. Every
  element carries its glyph with motion and without, and its text. A process the reader may not
  see, or one that does not exist, is answered `404` alike.
- A step of a version is drawn `running` while a run of the version runs it, and `planned` — at
  rest — otherwise. A version no run is running draws no motion.
- The visibility predicate answers for a process as well (`may_see_process`), the tenant boundary
  until UC-6.4.
- The web app draws the process level at `#/processes/<id>` and `#/processes/<id>/<version>`, live
  from the process's stream; the run level and the list of runs link to their process; the graph
  drawing is shared by both levels.
- `make generate` writes a process level into the web app's fixtures beside the run level.

## 2. The evidence

- Issue #190, its sections "How it is verified" and "Where the boundary lies"; UC-6.10 §1 and §2;
  ADR-0026; ADR-0063; ADR-0064; DEC-0055.
- `tests/integration/test_process_level.py`: a registered process read over HTTP from a daemon,
  with its autonomy statement and every glyph passing the check; a run of it followed on the
  process's stream within 5 seconds and listed by the level after; a new version changing the
  graph with nothing else edited, the earlier version read by name with its run.
- `tests/adapters/rest/test_process_level.py`, `tests/components/reporting/test_process_level.py`,
  `web/src/lib/process.test.ts`.

## 3. What was considered

- **A state *at rest* of its own in the vocabulary.** Rejected: it would draw as `planned` does,
  and the vocabulary's states are held equal to the run component's (ADR-0064).
- **The newest version by name as the default.** Rejected: a version name carries no order; the
  active version is the one that runs.
- **A count of runs per state on each step.** Rejected: that is the bottleneck analysis of
  UC-9.5, a figure with its own definition, not this level's.

## 4. Which entry permits it

M2.4, *"A change of what the software does, made inside an agreed scope, that breaks no
contract, moves no limit or autonomy level and says nothing public."* The scope is issue #190
under UC-6.10, accepted in DEC-0055, and ADR-0064. No contract under `contracts/` changes;
`api/openapi.yaml` is regenerated. No limit or level moves: the autonomy statement is shown, not
changed.
