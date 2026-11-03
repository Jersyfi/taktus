# ADR-0194 — A merge follows a written policy, and a change to a protected path halts the step with a request

**Status:** accepted · extends ADR-0088 (a step that asks), ADR-0192 (the processes of
software-operations select by a rule) and ADR-0193 (the repository connector's operations) ·
issue #439, UC-03 §4.7 B-7.12, §6 "Cheating to green"

## Context

UC-03 stage 4 adds B-7.12. A reviewing step that knows nothing of the author checks a green pull
request against a written policy, and merges narrow classes: patch updates, documentation.
Setting the policy stays with a person.

UC-03 §6 keeps "cheating to green" with a person at every stage. Cheating to green is changing
tests, security rules, feature flags or acceptance criteria to make something pass. A change to
the paths the tenant declares protected halts with a decision request. ADR-0192 left that row
unanchored, because the paths a change touches were not known at the step's boundary. ADR-0193
makes them known: the paths of a pull request at its head, and the paths of a worker's changeset
before it is written.

An anchor of the tenant's set is chosen by the step's actions: its capabilities and its operation
(ADR-0042). It is decided from the step's declaration, not from its resolved input. It cannot
tell a merge of documentation from a merge of tests: both are `repository.pullrequests.merge`.

## Decision

### 1. The merge operation

`repository.pullrequests.merge` merges one pull request at the head commit the caller names
(`sha`), by `merge` or `squash`. The commit message carries the key as a trailer. The lookup is
the pull request itself. Merged, with the key in its merge commit, is the original, replayed.
Merged without it is somebody else's merge: `conflict`. A head that is not `sha` is `conflict`,
so the paths read are the paths merged. A pull request the service will not merge is `conflict`.

### 2. The policy is the process version

The written policy of B-7.12 is its version. The classes it merges are `filter` conditions over
the paths and the title, `exact`, in the bundle a person registers. A tenant sets its policy by
registering its own version. Two classes are shipped:

| Class | Holds when |
|---|---|
| documentation | every changed path is documentation: under `docs/`, or a Markdown or plain-text file |
| patch update | every changed path is a dependency manifest or lock file, and the title says one dependency moves from `x.y.z` to `x.y.w`: the same major and minor version |

Nothing is merged when the pull request is not open, is a draft, or changes no path. Nothing is
merged when the service did not list its paths completely, or when its pipeline at that head is
not `success`. The reviewing step is given the paths, the title and the pipeline's word, never
the author.

### 3. A protected path halts the step with a request

The version declares the protected paths as a pattern. A rule counts the changed paths that match
it. Where the count is not zero, the step that would act does not run. A step of its own takes its
place, which carries `ask` (ADR-0088): a decision request to the deciding role, at every level,
which no tenant configuration removes. Declined, nothing is written.

B-7.12 does this before a merge, over the pull request's paths at the head it will merge. B-7.04
does it before a commit, over the paths of the worker's changeset. A repair that would change a
test to make the pipeline pass is asked, never written on its own.

## Alternatives

- **An anchor in the tenant's set for `repository.pullrequests.merge`.** It would halt every
  merge, the narrow classes too, and B-7.12 would never merge on its own. An anchor selects by
  action; the paths are a result of the step before it.
- **A new kind of anchor that selects by the paths in a step's input.** The anchor contract
  would have to read resolved inputs, for every tenant and every connector. The two processes
  that write code know their paths, and ask.
- **The policy as a file in the tenant's repository, read at the step.** The rules take their
  conditions from the bundle, not from a reading. A policy read as text could only be judged by a
  model, and the classes must be `exact`.
- **A model as the reviewing step.** It could merge a class the policy does not name. The
  policy's classes are fixed rules. The review of B-7.05 is a model's, and it merges nothing.

## Consequences

- `blueprints/software-operations/processes/` gains B-7.12, and B-7.04 its protected-path step.
- ADR-0192's boundary on "cheating to green" still holds for every other process.

## Where this promise ends

- **Only these two processes check paths.** P-03 of `dev-orchestration` writes a new branch and
  leaves the merge to a person. A process a tenant writes that commits or merges checks paths only
  where its version does.
- **A pattern protects what it names.** A protected file under a path the pattern does not match
  passes. The tenant's version names its paths.
- **A renamed file is checked under its new path.** The old path is not matched.
- **A patch update is read from the title.** A pull request whose title claims a patch while its
  lock file moves a minor version is merged as a patch. The pipeline at that head is what holds
  the change, and the tenant's update tool is what writes the title.
- **The decision request asks; it does not review.** A person who approves it merges or writes a
  protected change on their own judgement.
