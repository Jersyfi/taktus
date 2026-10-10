# NTC-0143 — The guides are published every day, and a hand edit is reported

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-10
**Raised in:** [#202](https://github.com/Jersyfi/taktus/pull/202), for issue #198

## 1. What was decided

Taktus publishes its guides as a process of its own, every day, as issue #198 requires (UC-13.6,
ADR-0066). Before, a person had to run `taktusctl guides publish`, and a hand edit reached only
whoever ran it. What the software does now:

- S-05 Guides (`blueprints/self-operation/processes/S-05-guides.yaml`) runs daily from its
  trigger. It reads the manifest and every file it names through `repository.files`, all at one
  commit; renders and measures the pages by rule; publishes them through `knowledge.pages`; and
  reports every page kept because a person's text stands.
- The reference repository connector reads up to 100 files at one commit in one call,
  `repository.files.read_many`.
- The loopback connector serves `orchestrator.guides`: sources, render, measure, publish and the
  report of a hand edit.
- An instance serves `knowledge.pages` over a directory where `TAKTUS_KNOWLEDGE_DIRECTORY` names
  one.

Four readings the issue leaves open were taken the strict way:

1. *The person the tenant configured as responsible for the documentation* is whoever the
   tenant's owner-facing channel reaches with the role `documentation`. The channel already says
   which roles reach the owner (ADR-0045 §3); a second register of responsible persons would be
   a parallel list (principle 1).
2. A tenant whose channel carries no such role cannot be told. The step that would tell fails
   and names the role, so the edit is not dropped silently, which UC-13.6 §2 forbids.
3. One edit is reported once. The report's identifier is derived from the page and the text that
   stands, and raising is idempotent by it. A daily report of the same edit would bury the next
   one (principle 9).
4. The report is a `need` with a date seven days after the run, configurable per trigger. A need
   holds what is needed, the steps, what stands still and a date (ADR-0028). A kind of its own
   would make every tenant's phrasebook invalid until its owner wrote new sentences.

## 2. The evidence

- Issue #198, its sections "How it is verified" and "Where the boundary lies".
- `tests/adapters/connectors/test_guides_process.py`: the bundle as shipped, against the fake
  repository service and the fake knowledge system — every page written and naming its commit;
  a merged change rewriting its page and no other; a hand edit kept and reported once; a page
  out of date on its contents page; a run that cannot tell anyone stopping at its report; the
  ledger entries of every step and the counts in the report.
- `tests/integration/test_time_triggers.py`: one run per day from the elected scheduler, with
  two schedulers running, and none after the process is switched off.
- `tests/adapters/connectors/test_repository_actions.py`: `repository.files.read_many` at one
  commit.
- `tests/components/knowledge/test_guides.py`: measuring as a rule over one reading, and a
  publication acting on that reading.

## 3. What was considered

- **Every hand edit reported again by every run.** Rejected for reading 3's reason.
- **Report a hand edit to the owner whatever the channel's roles.** Rejected: the issue says the
  tenant configures who is responsible; a tenant that did not configure it has not said that the
  owner is.
- **Let the run finish when nobody can be told.** Rejected for reading 2's reason.

## 4. Which entry permits it

M2.4, *"A change of what the software does, made inside an agreed scope, that breaks no contract,
moves no limit or autonomy level and says nothing public."* The scope is issue #198. The new
operations are declared by the connectors that serve them; no schema under `contracts/` changes.
No limit or level moves: S-05 is a new process at level 3. Nothing is published under the
project's name: the guides go to the knowledge system the tenant configured.
