# Examples

Worked examples that run against this repository as it is. Each is exercised by a test, so
that an example that stops working is a red gate, not a stale page.

| Example | Shows | Exercised by |
|---|---|---|
| [`processes/first-process.yaml`](processes/first-process.yaml) | the first process a new instance registers and runs, as the administration guide's last step: two `rule` steps and a `wait`, each confirmed by a person, nothing outside Taktus | `tests/integration/test_first_process.py` |
| [`processes/six-times-seven.yaml`](processes/six-times-seven.yaml) | the first control-plane slice end to end: a `rule` step, a `worker` step, a `wait` step, an `exact` step, and a step that admission control rejects before it starts | `tests/integration/test_first_slice.py`, `tests/exactness` |

## Running a process bundle

```bash
python3 workers/script/worker.py --port 9000 &
uv run taktusctl run --process examples/processes/six-times-seven.yaml
```

`taktusctl` lives in the project environment, hence `uv run`. With a database and the daemon
running (`uv run taktusd`, or `make up`), `uv run taktusctl submit --process …` queues the
bundle instead and prints the run's identifier; the daemon executes it, and
`GET /runs/{id}` shows where it got to. The command prints where the state
lives — the database named by `TAKTUS_DATABASE_URL`, or memory with a file snapshot, development
only — then the run, its steps, the ledger entries of the run with the result of verifying the
tenant's whole chain, the provenance of the run — one record per completed step — with the
result of verifying its chain, and the raw consumption against the budget. Exit code `0` means the run finished; `3` means it halted,
escalated or waits for a person, and the last lines say how to continue; `2` means the bundle or
the invocation is wrong, or a raise of its autonomy level is refused.

The example runs at autonomy level 2: no step starts before a person confirmed it (ADR-0039).
Each invocation therefore ends with the next step waiting and the line that confirms it:

```bash
uv run taktusctl run --process examples/processes/six-times-seven.yaml --resume <run> --approve prepare-commands
```

| Option | Meaning |
|---|---|
| `--resume RUN_ID` | continue a halted run at its step boundary. The bundle is read again: a changed `limits` block is a changed budget, which is how a run rejected by admission control is given more room. The steps a run executes are the ones it started with. A run still marked as running — its process was killed — is recovered: the step in flight goes back to its last persisted boundary and the run continues. |
| `--stop-after N` | request a stop after `N` steps have finished. The stop takes effect at the boundary; nothing is aborted. |
| `--approve STEP` | with `--resume`: confirm a step that waits for a person at level 2, and continue the run. Repeatable. `taktusctl submit --resume RUN --approve STEP` confirms it and hands the run back to the daemon |
| `--performed STEP` | with `--resume`: report that you performed the act of a step that Taktus only proposes at level 1, and continue the run. Repeatable |
| `--approve-raise` | approve, as the invoking person, a raise of the bundle's autonomy level over the version it replaces. It is admitted only with the quality history that version names under `autonomy.history`; a refusal is recorded in the ledger as `autonomy.refused` |
| `--worker URL` | the worker endpoint (default `http://127.0.0.1:9000`, or `TAKTUS_WORKER`) — for `TAKTUS_EXECUTION=endpoint`, the default. With `TAKTUS_EXECUTION=process` or `container` the command starts a unit per worker step instead, from the command line or image `TAKTUS_EXECUTION_UNIT` names (`.env.example`, `docs/architecture/contracts.md` §2.4); the bundle's `autonomy` decides whether `process` is allowed at all |
| `--state-dir PATH` | where artifact bytes are written, and — without a database — the snapshot of runs, plans and the ledger between invocations (default `~/.cache/taktus/taktusctl`, or `TAKTUS_STATE_DIR`). The snapshot is development only: the in-memory adapters, not a supported deployment. With `TAKTUS_DATABASE_URL` set the state lives in PostgreSQL (`README.md`, *Operating it*). |
| `--input NAME=VALUE` | one input of the run, repeatable; what `$input` references in the bundle resolve to. A value that reads as JSON is JSON (`--input issue=11` is a number, `--input labels='["taktus"]'` a list); anything else is text |
| `--identity ID` | the identity the command is attributed to and the run acts on behalf of — what every connector call carries. One the tenant knows (`taktusctl identity add ID`), or nothing executes; `TAKTUS_IDENTITY` when the option is not given. The command line authenticates by holding the instance's state, and the identity component supplies the organisational path (ADR-0040) |
| `--tenant ID` | the tenant the run belongs to (default `default`, or `TAKTUS_TENANT`): one the instance serves, as `taktusctl tenant list` shows. `taktusctl tenant create NAME` creates one and prints the identifier Taktus generated for it (ADR-0104). |

## Checking a bundle without an instance

```bash
uv run taktusctl bundle check examples/processes blueprints
```

`taktusctl bundle check` holds each bundle to the rules registration holds it to: the shape, the
rules of every step, the graph, and the exactness statement (ADR-0113). It is the code
registration runs, not a copy of it. It needs no instance, no database, no login and no network.
A path is a bundle file, or a directory: every YAML file below it is checked, except one whose
top-level `kind` says it is no process and that lists no steps, such as a `blueprint.yaml`. It
prints one line per bundle, and every finding of a refused one. Exit code `0` means every
bundle would register; `1`, that one would be refused; `2`, that a file cannot be read or that
no bundle was found.

Three refusals of registration need an instance and are not made here: a step naming a
credential that administers the instance's platform (ADR-0025), a raise of an autonomy level
over the active version (ADR-0039), and a version registered before with another content.

A repository that holds bundles runs the check in its own CI. On GitHub Actions:

```yaml
# .github/workflows/bundles.yml
name: bundles
on: [pull_request, push]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - name: Check the bundles as registration would
        run: uvx --python 3.13 --from "git+https://github.com/Jersyfi/taktus@v0.4.0" taktusctl bundle check processes/
```

`v0.4.0` is the first release that carries the command. Pin the release the instance runs, so
that the check holds the bundle to the rules that instance registers by. `processes/` stands for
wherever the repository keeps its bundles. The job needs no secret and reaches nothing but the
package's source. `tests/integration/test_bundle_check_command.py` runs the command in an
environment holding nothing of Taktus and holds this snippet to it.

## The shape of a bundle

The process bundle format proper arrives at `0.3.0` (`docs/roadmap.md`, ADR-0011). Until then a
bundle is the process version of `docs/architecture/control-plane.md` §4, written as YAML, with
one addition per step. Every field of a step is the shared kernel's `Step`
(`contracts/shared/v1/Step.json`) — `id`, `method`, `reason`, `rejected`, `exactness`,
`checks`, `fallback`, `model`, `requires`, `depends_on`, `role`, `expertise` — and the rules of
that schema hold: a result-producing step carries an exactness class, `wait` and `human` carry
none, `llm` and `worker` name a fallback, `ml` and `neural` pin a model, and `exact` admits
`rule` and `statistics` only. A `human` step and a fallback to a person name the role that acts
there, never a person; registration requires it once the tenant's identities hold a role
(ADR-0146), so the example's fallbacks name `owner`. An `exact` step also declares at least one check from the catalogue
(`contracts/shared/v1/Check.json`): `verify-answer` declares plausibility bounds, the pattern its
rule checks (ADR-0082). A bundle that breaks one of them is refused with every finding listed.
`uv run taktusctl exactness --process examples/processes/six-times-seven.yaml` prints the
bundle's exactness statement: which checks apply, what they cover, what they do not cover, and
what would slip through.

Top level:

| Field | Meaning |
|---|---|
| `id`, `version`, `name` | the process, its version, its name; the ledger refers to `id@version` |
| `autonomy` | the autonomy statement (ADR-0026): `level` — what the run and its worker assignments carry, 1 to 4 — `reason`, why the process runs at that level, and `toward_next`, what is missing to go one level higher or what forbids it (required below 4, absent at 4). A bare level does not register. Optional: `actions`, a lower level per tool action — a capability a step requires or a connector operation it calls — each with its own `level`, `reason` and `toward_next`; a step runs at the lowest level that applies to it. And `history`, how many runs in a row without a failure a raise of any of these levels needs (ADR-0039) |
| `limits` | the run's budget: `currency`, `quota` and `compute` in the shape of the worker contract's `Limits` (`contracts/worker/v1`). Every worker step's estimate is admitted against what is left of it. |
| `triggers` | what starts a run besides a person. `schedule` triggers are fired by the daemon's elected scheduler, once per slot (ADR-0035); `event` triggers are recorded, not yet acted on. A trigger is one of the two, see below |
| `expect` | when a run is expected (ADR-0107): `schedule`, in the form of a schedule trigger, a run at every slot; or `gap`, the longest time between the starts of two runs, as a duration (`26h`); and `bound`, the longest time a run may take from its start to its end. `schedule` and `gap` exclude each other. Without either, every schedule trigger expects a run at each of its slots. A run that was expected and did not start within the tenant's grace period, or did not end within its bound and the grace, raises an incident (`taktusctl incident`) |
| `open_work` | a cap per kind of open outcome (ADR-0132): `<kind>: {cap, reading, check_every}`. `cap` is how many outcomes of the kind may be open at once. `reading` is one read operation — `operation`, a literal `input`, `credentials`, and `select`, the dotted path to a list or a number in its output — that answers how many are open outside. Without a reading, only the process's runs in flight count. Before a run starts anything it counts both; at the cap it waits, booked to `wait.external`, and counts again every `check_every` (15 minutes). Only a person changes a cap: a version that changes one is registered only with `--approve-raise` |
| `deadlines` | the deadlines of each run, by name (ADR-0133): `<name>: {from, limit, lead, counts, until, at_lead, at_limit}`. `from` is `run`, `{after: <step>}` or `{date: <input>}`; `limit` and `lead` are durations (`1d`, `4h`, `0d`); `counts` is `calendar` or `working`, the tenant's working time; `until: {step: <step>}` names the step whose finish meets it. Each action is one of `{remind: <role>}`, `{escalate: <role>}` or `{start: {process, inputs}}`, never a person. A deadline without `at_limit` does not register. The elected scheduler takes each action once; `taktusctl deadline list` lists the open ones |
| `evaluation` | the process's evaluation cases (ADR-0134): `cases`, each an `id`, the run's `inputs` and `targets`, the result a step should produce, by step; `scorers`, each naming its `step`, a `method` — `rule`, with a `rule` of kind `equals`, `contains`, `pattern` (with its `pattern`) or `overlap`, or `llm`, a judge that rejects `rule` with why, names the model's `purpose`, its `criterion` and a `fallback` to a `rule` or to `human` — and its `reason`, `rejected` and `exactness` as a step carries them; and `schedule`, in the form of a schedule trigger, when the cases run with no change. A proposal that changes a step is run on the cases beside the active version when it is rehearsed, and commissioned only once it did not score lower by more than the tenant's tolerance, or with a person's reason |
| `slo`, `author`, `reason` | as in control-plane.md §4; recorded, not yet acted on |
| `steps` | the graph; edges are the `depends_on` lists. The graph is checked: acyclic, every dependency a step of the process, every step connected to the rest. |

A **schedule trigger** — `schedule:` with a five-field cron expression read in UTC, or `hourly`,
`daily`, `weekly` (Mondays 00:00 UTC) or `monthly` — starts a run of the version registered
last for its process, through `taktusd` with the `scheduler` role. A slot that passed before the
scheduler first saw the trigger does not fire; slots missed while no scheduler led start one
run, for the latest. A scheduled run has nobody to ask, so the trigger gives every input the
process declares, or the bundle does not register:

| Field | Meaning |
|---|---|
| `inputs` | fixed values, by input name |
| `each` | one run per item of a list: `operation`, a connector operation declared `read`; `select`, the dotted path to the list in its output; `field`, optionally, the dotted path to the value in each item; `input`, the input the value is given as |

The run acts for the identity that registered the version (`--identity` of the `run` or
`submit` that registered it, ADR-0040), and its ledger carries `run.triggered` beside
`run.created`. S-01 is the example:
weekly, one run per integration `orchestrator.integrations.list` answers
(`blueprints/self-operation/processes/S-01-removal-test.yaml`).

`work` per step — what the step does when it runs. Four method kinds are executable in this
version; every other method is refused before the run starts.

| Method | `work` | What happens |
|---|---|---|
| `rule` | `rule: constant` with `value` | the result is the value |
| `rule` | `rule: verify_artifact` with `step`, `artifact`, optional `pattern` | the result is the text of the named artifact of an earlier step, after its bytes are checked against the digest its producer announced and against the pattern. If either check fails, nothing leaves the step and the run escalates. This is the `exact` pattern of ADR-0014: a worker proposes, a rule produces the value. |
| `rule` | `rule: check` with `conditions`, each `value` and one or more of `equals`, `matches`, `not_matches` | the result is the checked values, once every condition holds over its resolved value — a pipeline's state equals `success`, an issue's body does not match a pattern. A value that is not a string is matched as its JSON text. A condition that does not hold escalates the run, naming the condition. The verdict comes from the values, never from a judgement: admissible for `exact` |
| `rule` | `rule: ready` with `expect`, `issue`, and for `expect: ready` also `open_records` and `open_issues` | the backlog's ready standard (`docs/process/README.md`, DEC-0051) over a repository's reading of one issue — the same module `make backlog` runs (`src/taktus/components/run/domain/service/ready.py`). `expect: ready` is an admission: the issue is open, not a pull request, not claimed, carries the three sections, a component, a milestone, one priority label and the label `ready`, and nothing it names under "Blocked by" is open — a record is open while its file is among `open_records` (file names, or entries with a `name`), an issue while it is among `open_issues` (numbers, or entries with a `number`). `handed: true` makes the admission one of an issue handed to Taktus: it also carries the label `to-taktus`, and its "Blocked by" names no ADR (DEC-0197). An issue labelled `decision-request`, `needs-owner` or `report` is refused as no work. `expect: sections_missing` holds when the issue is open, not a pull request, and lacks at least one of the three sections. The result is `{number, ready, reasons, missing}`; a refusal escalates the run naming every reason. Admissible for `exact` |
| `rule` | `rule: backlog` with `issues` and `open_records` | the backlog in its order (`docs/process/README.md`, DEC-0051) over a repository's readings of its open issues — the function `make backlog` prints from (`backlog()` in `src/taktus/components/run/domain/service/ready.py`). An issue that is a pull request or labelled `decision-request`, `needs-owner` or `report` is not part of it; an issue named under "Blocked by" is open while it is among `issues`. The result is `{ready, claimed, not_ready, disagreements, text, disagreements_text}`: the three groups in the order a session takes them, every issue labelled `ready` whose content fails the standard (an open blocker is not such a failure), and both as text. It never fails on what it finds. Admissible for `exact` |
| `rule` | `rule: roadmap` with `roadmap` and `issues` | the roadmap held against the open issues (`src/taktus/components/run/domain/service/roadmap.py`): every item of a milestone — the ` · `-separated list after a heading `` ### `X.Y.Z` `` up to `**Complete when**` — that names no issue `#N`, and every open issue that is work in a milestone whose items do not name it. The result is `{milestones, disagreements, disagreements_text}`; a text with no milestone escalates. Admissible for `exact` |
| `rule` | `rule: spam` with `text` (a text or a list of texts) and `patterns` | whether any of the patterns, regular expressions searched case-blind, occurs in the text. The result is `{spam, matched}`; it never fails on what it finds. Admissible for `exact` (UC-1.9, ADR-0088) |
| `rule` | `rule: classification` with `answer`, `screened` and `versions` | a contribution's class: `spam` where `screened`, a `spam` rule's result, found it; otherwise what `answer` — a text of lines `class:`, `version:`, `summary:`, or an llm step's whole result — names, held to `defect`, `feature` or `spam`, a defect or feature to one of `versions` and a summary. Anything else escalates. The result is `{class, version, summary}`; the class is the judgement's, so the step is never `exact` |
| `rule` | `rule: extract` with `values`, optional `excluding`, `pattern` and `text` | what a pattern names in a list of texts, less what it names in another: `values` and `excluding` are lists — nested lists read as one — of texts or of entries with a `path` or a `name`, as a changeset's files and a directory listing carry them; `pattern` is a regular expression with named groups, searched in each; `text` composes each match from its groups, `${group}`. The result is `{extracted}`, every distinct composed text of `values` that `excluding` does not compose too, sorted; nothing named is an empty list, an item of another shape escalates. Admissible for `exact`. P-03 derives with it the references that reserve the numbers of the records its change adds (ADR-0095) |
| `rule` | `rule: commit_title` with `title`, `number`, `types`, optional `labels` and `label_pattern`, `files` and `by_files`, `proposal` and `proposed` | a title in the Conventional Commits form, `<type>(<scope>): <summary> (#<number>)`, from a sentence (ADR-0101). The type is one of `types`, from the first source that gives one: the sentence where it is already in the form; a label `label_pattern` matches, its group `type`; the files — texts or entries with a `path`, nested lists read as one — where every one matches the `pattern` of an entry `{pattern, type}` of `by_files`; and `proposal`, a text in which `proposed` is searched, its groups `type` and `scope`. The summary is the sentence, its first letter lower-cased unless its first word is an abbreviation, a final full stop dropped; a scope that is not lower-case words is dropped. The result is `{title, type, scope, source}`. No type from any source, or two labels naming different types, escalates. Admissible for `exact`: a proposal is held to `types`, and the rule produces the title. P-03 titles its pull request with it |
| `rule` | `rule: invoice` with `invoice` and `order` | an incoming invoice, read as its EN 16931 business terms, computed again by the standard's calculation rules — each line, the lines' total, the total without tax, each tax category's amount rounded half up to the cent, the tax total, the total with tax, the amount due — and matched against the order or contract it names: currency, seller, the account to be paid, each line's price and open quantity, and the open total (ADR-0169). Any difference escalates and names each. The result is `{matched, document, order, supplier, currency, issue_date, due_date, net, tax, gross, payable, account, cost_centre, taxes}`, every amount as decimal text. Admissible for `exact`. B-10.03 of the invoice-to-payment blueprint checks every invoice with it |
| `rule` | `rule: template` with `text` and `values` | the result is the text with every `${name}` replaced by the named value (a value that is not a string as its JSON text); a name without a value escalates |
| `rule` | `rule: connector` with `operation`, `input`, `credentials` | the operation is called on the connector that declares its capability — every segment of the name but the last — with a call context the run builds: the run's identity, the step, the attempt and the idempotency key `taktus:<run id>:<step id>:<attempt>`, and the credentials by name (the connector's runtime holds the values). A read may carry `expect`, a list of `{select, equals | matches | not_matches}` over its output: a reading that does not show it fails the step, retryable, so that a resume reads again (issue #31); an expectation's optional `says` is what such a failure means, for a person, with each `${field}` of the reading put in, stated before the check that did not hold (ADR-0099). The result is what came back: `{output, effect, consumption}` of `contracts/connector/v1` §5. An effect the connector reports as `write` or `delivery` is written to the ledger as `egress.write` or `egress.delivery` beside `step.finished` (ADR-0022): the result has left the system. A classified failure escalates the run with the connector's cause; a resume retries with the same key when the connector said the failure was retryable, with a new attempt otherwise. An operation declared `idempotency: none` is never repeated by the run on its own — a failure with effect `unknown` escalates, and the reason says that resuming repeats the call, so that a person checks the target first (ADR-0024) |
| `wait` | `seconds` | the run waits through the clock port |
| `wait` | `until` with `operation`, `input`, `credentials`, `select`, `expect`, optional `poll_seconds` (30) and `timeout_seconds` (1800) | the run reads the operation — a read, never a write — every `poll_seconds` until the part of its output that `select` names is one of `expect`; past the timeout the step fails and the run escalates. A wait produces no result (ADR-0018); what the polls consumed is counted |
| `worker` | `task` (`goal`, `acceptance`, `inputs`), optional `max_steps`, `allowed_hosts`, `workspace`, `credentials`, `capacity_ceiling_seconds` | the task goes to a worker that offers every capability in `requires`, in a frame of exactly those capabilities and exactly the hosts in `allowed_hosts` (none, by default), with what is left of the budget as its limits; `credentials` name — never hold — what the assignment references, and the execution adapter (or whoever runs an endpoint worker) supplies the values (`CREDENTIALS.md`); a worker at capacity makes the step wait, and `capacity_ceiling_seconds` (one hour by default) is how long before the run escalates (ADR-0037) |
| `llm` | `purpose`, `prompt`, optional `system`, `values`, `max_output_tokens`, `pattern` | the prompt, with every `${name}` replaced from `values`, goes to the model configured for the purpose (`TAKTUS_MODEL_*`); the result is the text it answered, once it matches `pattern` — the check that keeps a `sourced` step from passing on an answer beside the point |

**When a step runs, and whom it asks first** (ADR-0088, ADR-0097). Beside what it does, a step's
`work` may carry keys of its own, for every method:

| Key | Meaning |
|---|---|
| `when` | a list of conditions in the shape of `rule: check`'s, over the results of the steps it depends on. When one does not hold, the step is skipped before anything of it starts: it succeeds with the result `{skipped: true, because}`, performs nothing and asks nobody, and the ledger says `step.finished` with the outcome `skipped`. A part a condition names that the result does not carry is null |
| `ask` | `question`, optional `situation`, `proposal` — templates over `values`, as a `template` rule's text is — `role` (`owner` unless named) and `on_decline` (`halt` or `continue`). Before the step's act, at every level, a decision request is raised for it, beside any anchor's (ADR-0042): perform the act (A, recommended) or not (B). A rehearsal asks nothing. Declined with `halt`, the run halts as for an anchor; with `continue`, the act is not performed and the step succeeds with `{declined: true, by, answer}` — the decider's answer as written — for the steps after it to act on |
| `on_escalation` | `true`: the step is no part of the sequence. When a step fails and the run escalates, the steps marked so run first, in the plan's order, each once every step it depends on succeeded; then the run ends escalated for the step that failed. A run that finishes skips them, with `{skipped: true, because: "the run did not escalate"}`. A step of the sequence may not depend on one, and one may not `ask`. P-03 gives its claim back with them |
| `empty_when_skipped` | `true`: a run that finishes with this step skipped, because its `when` did not hold, found nothing to do. It ends `empty`, not `ok` (ADR-0107). The step needs a `when`, and a step `on_escalation` may not carry it |
| `skills` | a list of skill names: the skills under the bundle's `skills/<name>/SKILL.md` the step uses (ADR-0113 §2). The run pins each at its version in production, or none while none is, and hands a step on a model or a worker their instructions in its brief; the step's method and exactness class stay its own (ADR-0162). `taktusctl skill register` registers a bundle's skills as drafts, and `bundle check` checks them |

P-05 Triage of contributions uses both: a step that closes spam runs only `when` the class is
spam, and the step that keeps a contribution `ask`s the owner first
(`blueprints/dev-orchestration/processes/P-05-triage.yaml`).

**References** inside the untyped parts of a step's work — a task's `inputs`, a connector call's
`input`, the `values` of a template, a prompt or a check's conditions, a wait's `input`:

| Reference | Replaced by |
|---|---|
| `{ $from: <step-id> }` | that step's result — the value a rule produced, the text an llm step produced, `{output, effect, consumption}` for a connector call, or `{artifacts: [...]}` for a worker step |
| `{ $from: <step-id>, $select: output.number }` | one part of it, by a dotted path over keys and list positions |
| `{ $from: <step-id>, $artifact: <artifact-id> }` | the content of that artifact: parsed when its media type is JSON, text otherwise |
| `{ $run: id }` | a part of the run's own record: `id`, `process_version`, `failed` — the step of the sequence that failed first and its reason, `{step, reason}`, or null while none has (ADR-0097) — or `keys.<step-id>`, the idempotency key that step's current attempt carries to a connector, its first attempt's while it has not started, so that an earlier step can ask whether what a later one will write is already its own (ADR-0099); `$select` applies here too |
| `{ $input: <name> }` | one of the run's inputs, given as `taktusctl run --input name=value` (a value that reads as JSON is JSON: `--input issue=11` is the number 11); `$select` applies here too |

A `$from` names a step that is a dependency, directly or through others. `$input` references are
resolved when the run is created and may therefore stand in typed places too — a workspace
location, an allowed host, a credential name. What a step read through a reference is recorded
in its provenance (ADR-0021); a read through a connector is recorded as an external source
with the moment and the digest of what it answered.

What every run does around every step, whatever the method, is stated in
`src/taktus/components/run/__init__.py` and ADR-0005.
