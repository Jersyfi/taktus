# NTC-0040 — P-02 and P-03 read the ready standard

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-08
**Raised in:** [#PR](https://github.com/Jersyfi/taktus/pull/PR)

## 1. What was decided

The ready standard is the backlog's rule for when a task can be worked: three sections — what
must be achieved, how it is verified, where the boundary lies — a component, a milestone,
exactly one priority label, the label `ready`, and nothing open under "Blocked by"
(`docs/process/README.md`, DEC-0051).

- **Old:** P-03 Implementation admitted an issue that was open, not a pull request, and carried
  a heading "## Acceptance criteria" in its body or a comment. **New:** P-03 admits an issue
  that meets the ready standard and is open, not a pull request and not claimed. A refusal names
  every reason. The admission is a `rule` step classed `exact`.
- **New:** P-03 claims the issue it admits with the label `in-progress` before the worker
  starts. A new run on a claimed issue is refused at admission; a stopped run goes on with
  `--resume`, or a person removes the label.
- **Old:** P-02 Refinement wrote a section "## Acceptance criteria" as a comment. **New:** P-02
  writes the sections of the standard that the issue's body lacks, and only those, as a comment.
  It refuses an issue that carries all three, and one it already commented on. It adds no label
  and does not edit the issue: a person, or P-01, puts the sections into the issue and adds
  `ready`. The model step stays `sourced`: its answer leaves only when it opens with one of the
  three headings and carries text under it.
- **New:** the standard is written once, as `src/taktus/components/run/domain/service/ready.py`.
  The run component's new built-in rule `ready` evaluates it, and `tools/backlog.py` loads the
  same file by its path. A process and a session therefore judge an issue by the same code.
- **How an open record is known.** A `NEED-NNNN` or `DEC-NNNN` blocks while its file is in the
  directory of open records on `main`. P-03 reads that directory through the connector; the
  directory is a run input, `records_path`, which is `docs/decisions/open` for this repository.
  An issue `#N` blocks while it is among the repository's open issues, which P-03 reads to the
  last page; a reading that stopped short fails its step.
- **The reference connector** gains two reads within the connector contract:
  `repository.issues.list` and `repository.files.list`. `repository.issues.read` now also
  returns the issue's labels by name and its milestone by title.
- P-02 and P-03 move to version 2 of their bundles. P-03 gains the required input
  `records_path`; `tools/first_run.sh` passes it.

## 2. The evidence

Issue #70 asked for this, from DEC-0051: Taktus taking over must change who executes, not how
the work is organised. Until now the bundles admitted by "Acceptance criteria", a heading the
backlog does not use. The issue form `Task` (`.github/ISSUE_TEMPLATE/task.yml`) renders the
three sections as `### ` headings, and `make backlog` reads them.

The tests:

- `tests/integration/test_dev_orchestration.py`: an issue made from the form and labelled
  `ready` is admitted and claimed. An issue missing a section, one without a milestone, and one
  blocked by an open record are each refused at admission with the reason. P-02 writes the one
  missing section of an issue as a comment and leaves a filled issue alone.
- `tests/exactness/test_exact_steps.py`: P-03's `admit` and P-02's `missing` are `rule` steps
  classed `exact` that run the rule `ready`.
- `tests/tools/test_backlog.py`: `make backlog` runs the same module, and the rule refuses for
  exactly the reasons the script lists.
- `tests/components/run/test_ready_rule.py` and `tests/adapters/connectors/test_repository_actions.py`.

The quota P-03 holds is unchanged at 200 units. Its reads before the wait for the pipeline grow
by about five requests: the open issues (one per page of 100), the directory (two) and the claim
(two). The wait reserves 162 units at its start. With the default margin of 0 the run keeps that
room; with a margin above about 8 % the wait could be refused, as it nearly could before.
Raising the quota is the owner's (M3.10), and nothing here raises it.

## 3. What was considered

- **The standard as `check` conditions with patterns in each bundle.** Rejected: "nothing open
  under Blocked by" needs the set of open records and issues, which a pattern cannot hold, and
  a second statement of the standard could drift from the one sessions use.
- **Open records known from the issues of decision and needs requests.** Rejected: the record's
  file is what `make backlog` reads, and the two can disagree for a while. On 2026-10-08 the
  issue of NEED-0012 was still open after its file had left `docs/decisions/open/`.
- **Only the issue numbers under "Blocked by".** Rejected: the standard names `NEED` and `DEC`
  records too, and the verification asks that an open record block.
- **P-03 reading the sections from P-02's comment as well as the body.** Rejected: the standard
  reads the body, and the person who adds `ready` is the one who accepts the sections into it.
- **P-02 adding `ready` itself.** Rejected by the issue: that waits for P-02's autonomy to be
  raised (M3.9).

## 4. Which entry permits it

M2.4: "A change of what the software does, made inside an agreed scope, that breaks no contract,
moves no limit or autonomy level and says nothing public." The scope is issue #70 under DEC-0051.
The connector contract is unchanged: two operations are added and a read gains fields, which
the contract leaves to the connector. No limit and no autonomy level moves.
