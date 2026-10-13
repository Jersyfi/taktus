# NTC-0203 — A coding change leaves the pipeline's workflow files alone

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-13
**Raised in:** the pull request for issue #366

## 1. What was decided

1. **P-03 asks its coding worker to leave `.github/workflows/` alone.** A new acceptance
   criterion of the step `implement` says that no file there is changed, and that a change
   the issue needs there is named in the summary, file and exact change, for a person to make.
2. **A refused write of a workflow file says so.** When the repository service refuses the
   tree of `repository.branches.create` as forbidden and the tree touches files under
   `.github/workflows/`, the failure names those files and that only an identity with the
   right to change workflows may write them. The cause stays `forbidden`, not retryable.
3. **The fake repository service refuses such a tree** with 403 "Resource not accessible by
   integration", as the service did.

## 2. The evidence

- 2026-10-13, the installed instance, `run_0fe0ff759342c538f0fd` for #256: the clone through
  the proxy worked (#356), the coding step succeeded for USD 0.69, and `create-branch` failed
  after nine blobs with "Resource not accessible by integration". The worker's changeset held
  `.github/workflows/ci.yml` (a changed comment) beside eight other files.
- CREDENTIALS.md, the row of the repository app's key: contents, issues and pull requests
  read and write; no right to change workflows.
- `tests/adapters/connectors/test_repository_actions.py`
  `test_a_refused_change_of_a_workflow_file_names_the_file` passes, and fails with the
  service's message passed through unchanged.

## 3. What was considered

- **Give the app the right to change workflows.** A workflow runs with the repository's
  secrets; Taktus would then write the pipeline that judges its own changes. The app's rights
  are recorded as they are, and this notice does not move them. Not taken.
- **Drop workflow files from the changeset in the run.** The branch would then differ from
  what the worker tested, in silence. Not taken.
- **Refuse in the connector before any request.** The connector does not know which rights
  its identity holds; another app may hold this one. Not taken.

## 4. Which entry permits it

M2.4 of `docs/decisions/anchors.taktus.md`: "A change of what the software does, made inside an
agreed scope, that breaks no contract, moves no limit or autonomy level and says nothing
public." The scope is issue #366. The connector's contract is unchanged: the cause and its
retryability stay as they were, only the detail says more. No limit, level or right moves.
