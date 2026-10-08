# Blueprint `dev-orchestration`

The blueprint of use case UC-01 (`docs/usecases/AF-01-dev-orchestration.md`): eleven processes
that drive a software product from its roadmap. `blueprint.yaml` describes all eleven — their
triggers, autonomy levels, steps and guardrails — as a curated template, in the shape the bundle
format of `0.3.0` will make binding.

Two of the eleven exist as bundles that run today, under `processes/`, in the shape
`examples/README.md` documents. The rest remain descriptions.

| Process | State | Bundle |
|---|---|---|
| P-01 Roadmap control | description | — |
| **P-02 Refinement** — an issue that lacks a section of the ready standard gains it as a comment | **runs** | [`processes/P-02-refinement.yaml`](processes/P-02-refinement.yaml) |
| **P-03 Implementation** — an issue that is ready becomes a pull request | **runs** | [`processes/P-03-implementation.yaml`](processes/P-03-implementation.yaml) |
| P-04 Review | description | — |
| P-05 Intake and triage | description | — |
| P-06 Consistency check | description | — |
| P-07 Quality reports | description | — |
| P-08 Decision request | description; the mechanism for this repository is ADR-0017 | — |
| P-09 Milestone report | description | — |
| P-10 Repository hygiene | description | — |
| P-11 Billing | later; the `finance` blueprint | — |

## The two that run

Both name capabilities only — `repository.issues`, `repository.comments`,
`repository.branches`, `repository.pipelines`, `repository.pullrequests`, `repository.labels`, `repository.files`;
`code.read`, `code.edit`, `code.test`, `shell.sandboxed`; the model purpose `reasoning` — and
configuration maps them to a connector, a worker and a model (`.env.example`: `TAKTUS_CONNECTORS`,
`TAKTUS_WORKER` or `TAKTUS_EXECUTION`, `TAKTUS_MODEL_*`). No product is named in either file.

Both read the backlog's **ready standard** (`docs/process/README.md`, DEC-0051): three
sections — what must be achieved, how it is verified, where the boundary lies — a component, a
milestone, one priority label, the label `ready`, and nothing open under "Blocked by". The
standard is one module, `src/taktus/components/run/domain/service/ready.py`, which the rule
`ready` evaluates and `make backlog` runs too, so that a process and a session judge an issue the
same way (issue #70).

**P-02 Refinement** (autonomy 3, seven steps): read the issue and its comments (`rule`, connector
reads), check that P-02 has not commented on it already (`rule`, `exact`), find the sections of
the standard the body lacks (`rule` `ready`, `exact` — an issue that is closed, a pull request,
or carries all three is refused here), write the missing ones (`llm`, `sourced` — the answer
leaves the step only when it opens with one of the three headings and carries text under it),
compose the comment (`rule`), write it (`rule`, outward effect: an `egress.write` entry in the
ledger). P-02 never edits the issue and never adds the label `ready`: a person, or P-01, puts
the sections into the issue and labels it, until P-02's autonomy is raised (M3.9). Run again on
the same issue, it stops at the first check: nothing is written twice.

**P-03 Implementation** (autonomy 4, seventeen steps): read the issue and its comments, compose
the context, read the repository's open issues (every page, or the step fails) and the directory
of open records on `main`, admit — the ready standard, and open, not a pull request, not claimed
(`rule` `ready`, `exact`; a refusal names every reason) — claim the issue with the label
`in-progress` (`rule`, outward), implement (`worker`, `tolerant`: the coding worker in a clone of
the repository, with the issue's text as its task and its section "How it is verified" as the
acceptance), name the branch, put the worker's changeset on it through the connector (`rule`,
outward: one commit that carries the idempotency key), wait for the pipeline (`wait`, polling
the pipeline's state), read the verdict, verify it is `success` (`rule`, `exact` — the pipeline's
verdict, never the worker's opinion), compose the title and the body, open the pull request
(`rule`, outward), label it (`rule`, outward). The body is the worker's summary between what
the template fixes: `Closes #N` and Taktus's own statement before it, and after it the section
the repository generates for the end of every description, copied verbatim from the run's
input `closing_section` — a copy is a rule, not a model's output (issue #34). Nothing writes to
the base branch: a person merges.

Every step carries its method, the reason, the alternatives rejected, a fallback where the
method can vary, and its exactness class; `tests/exactness` holds the `exact` steps to rules.
`tests/integration/test_dev_orchestration.py` runs both bundles end to end with the outside
faked — the repository service, the model endpoint and the coding agent — and everything inside
real: one comment with the missing section, the claim, one branch with the worker's files on
one marked commit, one pull request with one label, an egress entry for each write; and the
refusals — a filled issue left alone by P-02, an issue missing a section, one without a
milestone and one blocked by an open record refused by P-03 with the reason.

## Their autonomy, with the reason

Every process carries its level with its reason and what is missing to go higher (ADR-0026);
the bundles state it in full, and this is the short form.

| Process | Level | Why | Toward the next level |
|---|---|---|---|
| P-02 Refinement | 3 | the one outward effect is a comment a person reads before anything builds on it; the model's answer leaves only through a check; a second run writes nothing | a quality history — sections a person did not rewrite, over a month — and a stronger check on the answer's structure; then the raise is proposed (M3.9) |
| P-03 Implementation | 4 | nothing writes to a protected branch, the pipeline's verdict is the gate, a person merges, every outward effect is reversible until the merge; the worker runs in isolation with exactly the hosts and credentials the frame names **where the execution kind provides it** (DEC-0022) | — |

The last condition is the deployment's, not the bundle's. `container` and `cluster` enforce the
frame; `process` and `endpoint` do not, and with those two the isolation is whoever started the
worker's. A bundle cannot check how it is run, so the condition is named here and in the bundle
rather than assumed.

## Running them for real

`tools/first_run.sh <issue>` runs P-02 and then P-03 against this repository with the reference
connector, the coding worker and a configured model, from one command; `docs/runs/` holds
the record of what happened the first time. Run again — the normal case once an attempt found
a defect — it takes `--only P-03` to run one bundle with the same processes, and `--only P-03
--resume <run id>` to continue a stopped run. A P-02 that refuses the issue because it
carries every section, or because P-02 commented on it before, is reported as already done, and
P-03 runs; P-03 then admits the issue only once it meets the ready standard. A P-03 run claims
the issue with `in-progress`, and a new run on a claimed issue is refused at admission: the
way on after a stopped run is `--resume`, or a person removes the label. A branch
`taktus/issue-<n>` left by an earlier attempt stops the script before anything starts, with
the two ways on: resume the run that made it, or delete the branch and start again; the script
never deletes it (issue #30). The credentials it needs are parameters
(`CREDENTIALS.md`): the repository token, the coding agent's key or session token, and the
model endpoint's key if it needs one. The bundles' autonomy levels are the blueprint's; at level
3 and above the `process` execution adapter is refused (ADR-0002), so the coding worker runs by
endpoint or in a container. **`tools/first_run.sh` uses the endpoint kind and isolates
nothing**: it starts the worker as a plain process on the machine, with the machine's whole
network, which is a development shape and not what P-03's level-4 reason describes
(DEC-0022). An operating deployment uses `container` or `cluster`, where the frame is
enforced.

## What a run needs that the blueprint does not say

- **Inputs.** A bundle declares what a run is given (`inputs:` — name, description, example),
  and `taktusctl run --input name=value` supplies it. P-02 needs the issue number; P-03 needs
  it too, plus `records_path` — the directory of `main` that holds the open decision and needs
  records, `docs/decisions/open` here — the clone URL, the one host the worker may reach, the name of the coding
  worker's credential, and `closing_section`: the section the repository generates for the end
  of every pull request description, verbatim with its heading, or empty. The run cannot
  generate it — a template composes, it does not run the repository's generator — so whoever
  starts the run does, from the base branch; `tools/first_run.sh` runs
  `tools/check_status.py --print` on `main` for this repository. The triggers in
  `blueprint.yaml` will supply the other inputs from the event that starts a run, once event
  reactions exist (`0.2.0`). An automatic start will take the section from the worker, which runs the
  generator after its change (DEC-0037, decided); until then this input carries it.
- **The pipeline on a branch.** P-03 reads the pipeline's verdict before it opens the pull
  request, so the pipeline must run for a pushed branch; this repository's
  `.github/workflows/ci.yml` runs on pushes to `taktus/**` for that reason.
- **The guardrails** of `blueprint.yaml` (`no_push_to_protected_branches`, `ci_must_be_green`,
  `max_steps: 40`) are the bundle's own steps today: the connector opens a pull request and
  never pushes to the base, the `verify` step is the green check, and `max_steps` is the
  worker's frame. Governance rules that enforce them across processes are `0.2.0`.
