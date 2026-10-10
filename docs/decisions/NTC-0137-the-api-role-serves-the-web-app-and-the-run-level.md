# NTC-0137 — The `api` role serves the web app and the run level

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-10
**Raised in:** issue [#105](https://github.com/Jersyfi/taktus/issues/105), in the pull request that closes it

## 1. What was decided

The control plane now has a web app, and the first of UC-6.10's four levels, as ADR-0063
decides. Before, the HTTP surface answered JSON and a stream, and nothing drew. What the software
does differently:

- The `api` role serves `GET /levels/runs/{run_id}`: the run and each of its steps in order, with
  method kind, exactness class, state, what a waiting step waits on, what each step used and what
  the run consumed so far. Every element carries its glyph with motion and without, as the visual
  vocabulary gives it, and its text equivalent. It needs an account key in `Authorization`; a run
  the reader may not see is answered `404`, as one that does not exist.
- The `api` role serves `GET /vocabulary`, the visual vocabulary as one document, without a key.
- The `api` role serves the web app's static build at `{prefix}/app/` where the image holds it,
  and redirects `{prefix}/app` there. The image builds the web app in a stage of its own; its
  runtime holds the build and no Node.
- The web app asks for an account key, keeps it for the browser tab's session, lists the runs the
  tenant's stream shows, and draws a run's level live: it follows the run's stream and reads the
  level again on every change.
- A glyph's `edge` defaults to none, so that a run's glyph, which has no edge, reads back from its
  document. Nothing that draws a step changes.

Two choices ADR-0063 needed were made here. The text equivalent of a waiting step names the
account of ADR-0015 in words, the engine's cause token, the role a decision is addressed to and
the open decision requests — never a person, because a block names none. The figures are the run
component's quantities flattened into named numbers (`currency.eur`, `compute_seconds.<class>`,
`tokens_by_model.<model>.<kind>`), so that each has one name wherever it is shown.

## 2. The evidence

- Issue #105, its sections "How it is verified" and "Where the boundary lies"; UC-6.10 §1 and §2;
  ADR-0055; ADR-0059; ADR-0063; DEC-0055.
- `tests/integration/test_run_level.py`: a registered process's run read over HTTP from a daemon,
  every glyph passing the check, the figures equal to the run's own as `GET /runs/{id}` gives it,
  a waiting run saying on what with nothing moving, a key of no identity refused.
- `tests/adapters/rest/test_levels.py` and `tests/components/reporting/test_run_level.py`; the
  web app's tests under `web/src/`.

## 3. What was considered

- **Name the person a step waits on.** Rejected: a block names no person (ADR-0015, protective
  rule), and UC-6.10's "on whom" is answered by the role a decision is addressed to.
- **Count the run's in-flight reservation into each step's figure.** Rejected: the run component
  sums reservations into the run's total (`Run.consumed`); a step shows what it recorded it used,
  so that no figure is computed a second time in `reporting`.
- **Answer a run of another tenant `403`.** Rejected: ADR-0055 §5 says what a reader may not see
  is absent, and a `403` would say it exists.

## 4. Which entry permits it

M2.4, *"A change of what the software does, made inside an agreed scope, that breaks no
contract, moves no limit or autonomy level and says nothing public."* The scope is issue #105
under UC-6.10, accepted in DEC-0055, and ADR-0063. No contract under `contracts/` changes; the
surface's own interface grows, and `api/openapi.yaml` is regenerated. No limit or level moves.
The web app is served by an instance to its own readers and says nothing under the project's name.
