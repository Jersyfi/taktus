# NTC-0023 — The repository connector acts as the app when configured

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-08
**Raised in:** [#108](https://github.com/Jersyfi/taktus/pull/108)

## 1. What was decided

Four things the software does differently, all inside issue #99 and DEC-0058:

- **The reference repository connector acts as Taktus's own app** when two variables name the
  app: its identifier and the file of its private key. It then mints an installation token from
  the key, for its one repository, holds it in memory while more than five minutes are left,
  and replaces it before that. What it writes appears under the app's name. Before, it acted
  only with a token placed in its environment, as whoever owned that token. Without the two
  variables it still does exactly that.
- **One of the two variables without the other stops the connector at start**, with the name of
  the missing one. Before, neither existed.
- **`tools/first_run.sh` chooses the app when the two variables are set**, and the repository
  token otherwise. It refuses half of the app's configuration before it starts anything.
- **The workflow `live` runs the connector's test as the app**, and fails when the scratch
  repository is named but the app is not configured, and when the test skipped instead of
  passing. Before, a skipped test left the job green.

## 2. The evidence

- DEC-0058, the decision: an app of its own, tokens that live an hour and are never stored.
  NEED-0013: the app exists and is installed on this repository and the scratch repository.
- `tests/adapters/connectors/test_repository_app.py`: minting, holding, replacing before expiry,
  the app's name on what it writes, one bound name and no fallback, each refusal with its
  reason, and no key, token or signed statement in a result, an error or the log.
- `tests/conformance/`: the suite passes against the connector as the app, and a connector whose
  app serves a call without a credential fails C-03.
- `tests/tools/test_live_workflow.py`: the key's file lies outside the job's evidence and is
  removed when the step ends.

## 3. What was considered

- **Mint the token in the workflow with a ready-made action and hand it to the connector.** Not
  taken: the live test would prove the token mode, and the minting this change introduces would
  meet the real service for the first time on the installed instance (ADR-0033, Alternatives).
- **Mint a new token for every call**, with no token held. Not taken: two more requests per call,
  for no gain in what can leak — the token would sit in memory for the length of the call either
  way.
- **Treat half of the app's configuration as "no app".** Not taken: an operator who set one of the
  two meant the app, and acting as a person instead would be the very thing DEC-0058 removed.

## 4. Which entry permits it

M2.4: a change of what the software does, inside the agreed scope of issue #99 (DEC-0058), that
breaks no published contract — the connector contract is unchanged and its suite passes in both
modes — moves no limit or autonomy level, and says nothing public. Which identity Taktus uses was
decided by DEC-0058; how the connector carries it out is this notice.
