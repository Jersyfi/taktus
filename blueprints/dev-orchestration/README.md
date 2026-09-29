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
| **P-02 Refinement** — an issue without acceptance criteria becomes one with them | **runs** | [`processes/P-02-refinement.yaml`](processes/P-02-refinement.yaml) |
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
`repository.branches`, `repository.pipelines`, `repository.pullrequests`, `repository.labels`;
`code.read`, `code.edit`, `code.test`, `shell.sandboxed`; the model purpose `reasoning` — and
configuration maps them to a connector, a worker and a model (`.env.example`: `TAKTUS_CONNECTORS`,
`TAKTUS_WORKER` or `TAKTUS_EXECUTION`, `TAKTUS_MODEL_*`). No product is named in either file.

**P-02 Refinement** (autonomy 3, six steps): read the issue and its comments (`rule`, connector
reads), check that it is open, not a pull request and without criteria (`rule`, `exact`), derive
the criteria (`llm`, `sourced` — the answer leaves the step only when it is the section asked
for with at least one checklist item), compose the comment (`rule`), write it (`rule`, outward
effect: an `egress.write` entry in the ledger). Run again on the same issue, it stops at the
check: the criteria are there, nothing is written twice.

**P-03 Implementation** (autonomy 4, fourteen steps): read the issue and its comments, compose
the context, admit — open, not a pull request, criteria present (`rule`, `exact`) — implement
(`worker`, `tolerant`: the coding worker in a clone of the repository, with the issue's text as
its task), name the branch, put the worker's changeset on it through the connector (`rule`,
outward: one commit that carries the idempotency key), wait for the pipeline (`wait`, polling
the pipeline's state), read the verdict, verify it is `success` (`rule`, `exact` — the pipeline's
verdict, never the worker's opinion), compose the title and the body, open the pull request
(`rule`, outward), label it (`rule`, outward). Nothing writes to the base branch: a person
merges.

Every step carries its method, the reason, the alternatives rejected, a fallback where the
method can vary, and its exactness class; `tests/exactness` holds the `exact` steps to rules.
`tests/integration/test_dev_orchestration.py` runs both bundles end to end with the outside
faked — the repository service, the model endpoint and the coding agent — and everything inside
real: one comment, one branch with the worker's files on one marked commit, one pull request
with one label, three egress entries.

## Their autonomy, with the reason

Every process carries its level with its reason and what is missing to go higher (ADR-0026);
the bundles state it in full, and this is the short form.

| Process | Level | Why | Toward the next level |
|---|---|---|---|
| P-02 Refinement | 3 | the one outward effect is a comment a person reads before anything builds on it; the model's answer leaves only through a check; a second run writes nothing | a quality history — criteria a person did not rewrite, over a month — and a stronger check on the answer's structure; then the raise is proposed (M3.9) |
| P-03 Implementation | 4 | nothing writes to a protected branch, the pipeline's verdict is the gate, a person merges, every outward effect is reversible until the merge; the worker runs in isolation with exactly the hosts and credentials the frame names **where the execution kind provides it** (DEC-0022) | — |

The last condition is the deployment's, not the bundle's. `container` and `cluster` enforce the
frame; `process` and `endpoint` do not, and with those two the isolation is whoever started the
worker's. A bundle cannot check how it is run, so the condition is named here and in the bundle
rather than assumed.

## Running them for real

`tools/first_run.sh <issue>` runs P-02 and then P-03 against this repository with the reference
connector, the coding worker and a configured model, from one command; `docs/runs/` holds
the record of what happened the first time. The credentials it needs are parameters
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
  it too, plus the clone URL, the one host the worker may reach, and the name of the coding
  worker's credential. The triggers in `blueprint.yaml` will supply these from the event that
  starts a run, once event reactions exist (`0.2.0`).
- **The pipeline on a branch.** P-03 reads the pipeline's verdict before it opens the pull
  request, so the pipeline must run for a pushed branch; this repository's
  `.github/workflows/ci.yml` runs on pushes to `taktus/**` for that reason.
- **The guardrails** of `blueprint.yaml` (`no_push_to_protected_branches`, `ci_must_be_green`,
  `max_steps: 40`) are the bundle's own steps today: the connector opens a pull request and
  never pushes to the base, the `verify` step is the green check, and `max_steps` is the
  worker's frame. Governance rules that enforce them across processes are `0.2.0`.
