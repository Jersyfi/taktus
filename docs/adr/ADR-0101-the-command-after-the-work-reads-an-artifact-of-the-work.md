# ADR-0101 — The command after the work reads an artifact of the work

**Status:** accepted · extends the worker contract of ADR-0007 by one optional field of the
command after the work (ADR-0053), and check W-18 by what that command reads · issue #471

## Context

The description of a pull request P-03 opens is the coding agent's summary, with the section the
repository generates appended. The repository checks a description in its `description` check,
`tools/check_decisions.py --pr-body`, which runs only on a pull request.

On 2026-10-16 #470 was green in every check except `description`. The agent's summary quoted a
reference as "(ADR 0034, …", and the check reads the ellipsis as a placeholder. A session fixed
the description by hand. The agent had run every other check in its workspace (ADR-0100). The
description is assembled after the coding step, so nothing checked it before the pull request
was opened.

The run executes no repository code itself: that is the adapter obligation. The one place where
the repository's own code runs after the summary exists is the worker's command after the work.
That command could not see the summary: it is an artifact of the assignment, not a file of the
workspace.

## Decision

### 1. The command after the work may read an artifact
The worker contract's `AfterCommand` gains an optional `input`: the `artifact_id` of an artifact
the assignment produced before the command.

- The worker gives the command that artifact's content on its standard input, byte for byte.
- An assignment that produced no artifact of that id fails, and the command does not run.
- Without `input`, the command's standard input is empty.

Everything else about the command stays as ADR-0053 states it. Check **W-18** holds a worker to
the new half too. The suite's run `before-command` gains a command after the work, `cat`, that
reads the artifact of the command before the work as its `input`. What it prints must be the same
bytes. All four workers pass it.

### 2. P-03 checks the description before it opens the pull request
P-03 version 17 names `python3 tools/describe.py` as its command after the work, with `input:
summary`. The tool puts the summary and the generated section together as P-03's template does.
It runs `tools/check_decisions.py --pr-body --description-only` on the result. It prints the
generated section only when that passes. Otherwise it exits with 1, the check's findings last on
its error output.

So a summary the check fails fails the coding step. The run gives the issue back, and its comment
quotes the findings (ADR-0097). No branch is written and no pull request is opened. The agent's
acceptance names the command, so that the agent runs it on its summary before it ends.

`--description-only` runs the checks that read the description and leaves the rest of the
register out. That rest is `make gate-decisions`, which the pipeline runs on the branch before
P-03 opens the pull request.

## Alternatives

- **The agent checks its own summary, and nothing else.** That is what #470 had: an agent that
  ran every check it was told to. A check the run depends on is run by the run's mechanics, not
  left to a model's diligence.
- **A second worker step after the body is composed.** It would check the exact text, at the cost
  of a second assignment, a second workspace and a second clone per run. The composed text
  differs from what the tool checks only by `Closes #N` and Taktus's statement before the
  summary. Neither carries a heading, so the check reads the same sections in both.
- **The agent writes its description into a file the command reads.** The pull request would then
  carry the file, not the summary. A second source for the same text can drift from the first.
- **The rule in the core.** The core would copy the repository's check into the product. It would
  name one project's conventions there (ADR-0092), and drift from the check CI runs.

## Consequences

- `contracts/worker/v1`: `AfterCommand.input`; README §3 and §7, CONFORMANCE.md. Additive: a task
  without `input` is unchanged.
- `ports/worker.py`: `AfterCommand.input`.
- The four workers give the artifact to the command. The conformance suite's `before-command`
  run checks it.
- `tools/describe.py` is new. `tools/check_decisions.py` gains `--description-only`.
- P-03 becomes version 17. Its coding step now fails on a description the check fails, after it
  spent its money. The change is lost with it, as with any failed coding step.

## Where this promise ends

The tool checks the summary with the generated section, not the description as the run finally
composes it. A section handed in as the input `closing_section` replaces the generated one after
the check. What the run puts before the summary is not checked either.

The check is `description` as the branch's tree states it. A description check that the base
changes after the branch was made is not seen. A pull request edited after it was opened is the
pipeline's to check again, as before.

A summary the check fails is not corrected by the run. The agent is asked to run the command
itself and correct its summary until it passes. When it does not, the run gives the issue back:
the coding step's money is spent, and its change is not kept.

The suite sees that the command read the artifact. It does not see whether a worker gave the
command anything else.
