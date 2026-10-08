# NTC-0048 — P-01 reports where roadmap and backlog disagree

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-09
**Raised in:** PULL_REQUEST

## 1. What was decided

P-01 Roadmap control, until now a description in the dev-orchestration blueprint, runs as a
bundle: `blueprints/dev-orchestration/processes/P-01-roadmap-control.yaml`.

- **Old:** nothing held the roadmap against the issues; a session did it by hand, when it
  remembered to. **New:** P-01 reads the roadmap on `main`, the open issues to the last page and
  the directory of open records, and writes one report. The report names every item of a
  milestone that names no issue, every open issue in a milestone whose items do not name it,
  and every issue labelled `ready` whose content fails the ready standard. It also prints the
  backlog in its order.
- **The report is a comment on one fixed issue**, given to the run as `report_issue`. It is an
  outward write, recorded as an `egress.write` entry in the ledger. P-01 creates no issue, sets
  no milestone or label, and closes nothing: it proposes, a person acts (issue #71, M3.9).
- **The order is computed once.** The grouping and the order of the backlog — ready, claimed,
  not ready; earliest milestone, then priority, then issue number — move into the module that
  already holds the ready standard, `src/taktus/components/run/domain/service/ready.py`, as
  `backlog()`. `make backlog` prints from it, and the run component's new rule `backlog` runs
  it. A process and a session cannot order the same issues differently.
- **The reconciliation is a rule**, the run component's new rule `roadmap`
  (`domain/service/roadmap.py`): it reads the issue numbers each roadmap item names. Both new
  rules are classed `exact`; P-01 asks no model. Whether the reconciliation stays a rule is the
  owner's (M3.13) and asked in DEC-0080; the rule is the provisional answer.
- **An issue labelled `ready` that is blocked by an open record or issue is not reported.** The
  label claims the content of the standard (points 1 to 5); what blocks is read when the backlog
  is read (`docs/process/README.md`). The report compares the label with the content only.
- **A label `report` marks an issue that is not work**, beside `decision-request` and
  `needs-owner`. The issue that carries P-01's reports carries it, so that neither `make
  backlog` nor P-01 counts it.
- P-01's autonomy level stays 3, the blueprint's. Its reason now says what the bundle does: the
  one outward effect is a report a person reads, every verdict in it is a rule's, and a person
  applies what it proposes.

## 2. The evidence

Issue #71 asked for this, from DEC-0051 and the blueprint's description of P-01.

- `tests/integration/test_dev_orchestration.py`: P-01 through `taktusctl run` against the
  reference connector and a faked repository service. A consistent roadmap and backlog yield a
  report whose two lists of disagreements say `none`. A roadmap and backlog with every kind of
  disagreement yield each disagreement exactly once, and an issue blocked by an open record is
  not among them. In both, the order in the report equals what `tools/backlog.py` computes for
  the same issues, one comment is written, one `egress.write` entry, and no label changes.
- `tests/components/run/test_roadmap_rule.py`: both rules as tables.
- `tests/tools/test_backlog.py`: the script and the rule give the same groups, in the same
  order, with the same reasons.
- `tests/exactness/test_exact_steps.py`: `order` and `reconcile` are `rule` steps classed
  `exact`, and every step of P-01 is a rule.
- Run by hand on this repository's roadmap and open issues on 2026-10-09: no issue the roadmap
  does not place, no `ready` label on failing content, and 24 items of `0.3.0` to `1.0.0` that
  no issue carries yet.

The run's quota is 40 units: two for the roadmap, up to twenty for the issues, two for the
directory, three for the comment.

## 3. What was considered

- **The report as a new issue on every run.** Rejected: a daily issue floods the backlog it
  reports on, and each would itself be counted as work.
- **The report as a file of the run, read with `taktusctl`.** Rejected: issue #71 asks for a
  report a person reads, and a person reads the repository's issues, not the run's files.
- **One comment edited in place.** Rejected for now: the connector has no operation to edit a
  comment, and a comment per run keeps the history of what was reported when.
- **The order computed in the bundle by its own rule.** Rejected: issue #71 asks for the same
  rule `make backlog` runs, and #70 set the precedent of one shared module.
- **Reporting a `ready` label on a blocked issue.** Rejected: `docs/process/README.md` says a
  blocked task keeps its label and is offered once its blocker closes.

## 4. Which entry permits it

M2.4: "A change of what the software does, made inside an agreed scope, that breaks no contract,
moves no limit or autonomy level and says nothing public." The scope is issue #71 under DEC-0051.
No contract changes: two built-in rules are added to the run component, and the connector is
unchanged. P-01's level stays 3; only its reason is restated. The method of the reconciliation
is not decided here: it is asked in DEC-0080.
