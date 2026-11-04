# ADR-0193 — A pull request is kept mergeable on its own branch, through the repository service

**Status:** accepted · extends ADR-0024 (a lookup reads only what the service answers as
written), ADR-0099 (a branch read before it is written) and ADR-0192 §2 (the processes of
software-operations) · issues #400, #439, UC-03 §4.1, §4.7

## Context

UC-03 stage 0 adds B-7.04: open pull requests kept mergeable. That means three things: brought
up to date with their base, the pipeline repaired, review comments worked in. Stage 4 adds
B-7.05 (a review of every pull request), B-7.10 (abandoned work reported) and B-1.12 (the
pipeline's lost and hung runs). The repository connector could read one pull request and create
a branch. It could not list the open pull requests, say which of them is behind its base or red,
bring a branch up to date, or write onto a branch that already exists. Every change it wrote was
a new branch (`repository.branches.create`). The coding worker of `dev-orchestration` P-03
proposes a changeset; it cannot push, and must not (ADR-0089).

## Decision

### 1. The repository connector gains five operations

All of them use the service's documented interface; none is a judgement of the connector's.

| Operation | Effect | What it does, and how a repeat is recognised |
|---|---|---|
| `repository.pullrequests.list` | read | the pull requests in one state, each with its head, the head's commit, its base, whether it is a draft, its labels, and two ages in whole hours at the moment of the reading: `idle_hours` since its last update and `open_hours` since it was opened. With `with_state: true`, for at most 30 of them, also `behind` and `ahead` (commits, from the service's comparison of base and head), `pipeline` (the word of `repository.pipelines.status` for the head) and `head_key` (the idempotency key the head commit carries as a trailer, or null) |
| `repository.pullrequests.files` | read | the paths a pull request changes, at the head commit it names: each path with its status and its lines added and removed, and the patch where `patches: true`; the sums, `count`, and `complete`, false when the service listed more than it answers |
| `repository.branches.update` | write, `marked` | the base merged into a branch through the service's merge interface, in one commit whose message carries the key as a trailer. The lookup is the head of the branch: a head that carries the key is the original, replayed. A branch that already contains its base gets no commit and `updated: false`. A merge with a conflict is `conflict` and writes nothing. With `expected`, a head that is another commit is `conflict` before anything is written |
| `repository.branches.commit` | write, `marked` | one commit with the given files on top of an existing branch, through the object interface, the key as a trailer. The lookup walks the branch's first parents from its head, at most 20: a commit carrying the key is the original, replayed. `expected` is required: the commit the change was made against, which must be the head; another head is `conflict`. The reference moves only forward; the service's refusal of a move that is not a fast-forward is `conflict` |
| `repository.pipelines.list` | read | the pipeline runs in one status — `queued`, `in_progress` or `completed` — newest first, at most 100, each with its head commit and `age_minutes` since it was created, at the moment of the reading |

A file a commit writes keeps the mode it has in the branch, as `repository.branches.create`
keeps it (DEC-0020). The service refuses Taktus's app a file under the pipeline's own
definitions, on an existing branch as on a new one (#366).

### 2. B-7.04 writes onto the pull request's own branch

B-7.04 reads the open pull requests with their state and takes one per run. It must not be a
draft, its head must match the version's pattern of branches it keeps, and it must be behind its
base or red. A red one whose head commit Taktus wrote is left out: its key is at the head. A
repair Taktus made that the pipeline still refuses goes to a person, not to the next repair
(UC-03 B-11.07). Of the rest, the one idle longest is taken.

A pull request behind its base has the base merged into it (`repository.branches.update`). A red
one is repaired by the coding worker in a clone of its branch, under the version's acceptance.
The changeset goes onto the same branch (`repository.branches.commit`), with `expected` set to
the commit the worker cloned. A head that moved meanwhile is a conflict, and nothing is written
over another's work.

The branch the worker clones is known only once a step before it has selected the pull request.
A worker step's `workspace.ref` may therefore be a reference to an earlier result, `{"$from": …}`,
as a task's inputs may be. It is resolved when the step runs, as the inputs are; a reference that
does not resolve to a text fails the step before anything is handed to the worker.

### 3. Ages are the connector's arithmetic over the service's timestamps

`idle_hours`, `open_hours` and `age_minutes` count whole units between the service's own
timestamp and the connector's clock at the moment of the reading, rounded down. They are part of
the reading and recorded with it. A rule over them (`filter`, `at_least`) is therefore
reproducible from the reading. The service's timestamp is never changed.

## Alternatives

- **The service's update-branch interface.** It answers asynchronously, with no commit, and its
  commit cannot carry a key. A repeat could not be told from a second update, and a wait for the
  pipeline could read the old head. The merge interface answers with the commit.
- **A rebase instead of a merge.** A rebase rewrites the branch, which loses what a reviewer
  commented on. The service offers no rebase of a branch through its interface.
- **Force-pushing the worker's result.** It would overwrite whatever a person pushed meanwhile.
  `expected` and a forward-only move refuse that.
- **One run per pull request, by event.** A push to the base makes every open pull request
  behind at once. One run per pull request would start them all, and the cap on open work
  (B-11.03) would have nothing to order them by. One run takes one: the one idle longest.
- **The service's own mergeability word.** It is computed asynchronously and often unknown on the
  first read. The comparison's `behind` and the pipeline's state are answered as written.

## Consequences

- The repository connector declares five more operations. Its fake serves the interfaces they
  use: the comparison, the merge, a pull request's files, a reference moved forward, the runs by
  status.
- A pull request reading carries the head's commit and whether it is a draft. An issue reading
  carries `updated_at`, and an issue list `idle_hours`.
- The run's worker work gains `workspace_ref`: a reference under `workspace.ref` is moved there
  when the work is read, and resolved when the step runs.

## Where this promise ends

- **A conflict is not resolved here.** A merge of the base that conflicts writes nothing and ends
  the step in `conflict`; the run goes to a person. Resolving it in the worker's clone is a later
  version of B-7.04.
- **A red pipeline after Taktus's own commit stays with a person.** That includes a base merged
  in by Taktus that made the pipeline red.
- **`with_state` reads at most 30 pull requests.** A repository with more open ones has the rest
  left out of that run, and `complete` says so.
- **The lookup of `repository.branches.commit` walks 20 commits.** A repeat after twenty other
  commits on the branch would act again. A commit somebody else pushed in between moves the head,
  and the repeat then ends in `conflict` instead.
- **An age is as exact as two clocks.** The service's timestamp and the connector's clock may
  differ by seconds. An age is whole hours or minutes and a rule over it a threshold, so such a
  difference moves an item across a threshold at most once.
- **Review comments are read as context only.** The worker is given the pull request's comments.
  Whether a comment was worked in is the reviewer's verdict, not the connector's.
