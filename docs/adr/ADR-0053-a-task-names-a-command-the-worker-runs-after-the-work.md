# ADR-0053 — A task names a command the worker runs after the work

**Status:** accepted · builds DEC-0037's Option A for the automatic start of P-03 (issue #77);
extends the worker contract of ADR-0007 by one optional field of the task and one check

## Context

Every pull request description of this repository ends with a section a program generates:
`tools/check_status.py --print`. The description check compares that section with what the
program prints on the pull request's branch. A copy of it is a fixed operation, so no model may
produce it (issue #34). P-03 Implementation therefore appends the section by a template, from its
input `closing_section`. Whoever starts the run by hand runs the program and hands in the output.

A run started by an event has nobody to ask. Its trigger must give every input the process needs
(ADR-0048 §7), and no trigger can give a text that only the repository's code computes. DEC-0037
decided where the section comes from then: the worker, after its change, runs the command the
bundle names in its workspace and publishes the output as an artifact the run appends.

Two things were missing. The worker contract had no way to name a command that runs after the
work. A process bundle had no way to say that an input may be left out because a step produces
what stands in for it.

## Decision

### 1. The task may name a command after the work
The worker contract's `Task` gains an optional `after`: a `command`, as a program and its
arguments, and the `artifact` identifier its output is published under.

- The worker runs the command once the work is done, as the assignment's last step, in its
  workspace. For a coding worker that is the tree its changeset describes.
- The command runs without a shell. The worker gives it no credential.
- Its standard output becomes the named artifact, byte for byte, with media type `text/plain`.
- A command that exits with anything but 0 fails the assignment, and the artifact is not
  produced.
- The command is the task's, not the agent's. No model chooses it, runs it or touches what it
  prints.

Conformance check **W-18** holds a worker to this. The suite runs the same work twice with a
command after it: one prints a value only that run knows, which must come back as the artifact
byte for byte after every step of the work; the other exits with 1, which must fail the
assignment without the artifact. Both reference workers pass it.

### 2. An input may be optional, and a reference names what stands in for it
An input declaration in a bundle may say `required: false`. A run may then start without it, and
a trigger need not give it. A reference to such an input names what stands in for it:
`{ $input: <name>, $otherwise: <value> }`. The value may be a `$from` reference, so that an
input given by hand and a step's output can stand for each other. When the run was given the
input, the step the `$otherwise` names is not read for it.

### 3. P-03 uses both
P-03 version 5 has its implementing worker run `python3 tools/check_status.py --print` after the
work, published as `closing`. A template step puts it under the section's heading. The body takes
the input `closing_section` where whoever started the run gave one, and otherwise that step. The
input is optional, and the trigger of the blueprint's `issue.ready` is in place.

## Alternatives

- **A stored copy of the section, read at the branch** (DEC-0037 Option B). It reverses part of
  DEC-0026: two pull requests that change the register conflict on that file again.
- **Whoever starts the run computes the section** (DEC-0037 Option C). Every automatic start of
  P-03 would need a copy of the repository and the program: a special case in the scheduler and
  the automation role.
- **Asking the coding agent to run the program and paste the output.** A copy by a model is what
  issue #34 took away; the first live run lost four attempts on it.
- **Removing the input `closing_section`.** The manual start keeps it (issue #77, "Where the
  boundary lies"); an optional input with a stand-in keeps it without making every start give it.
- **A default value on the input declaration.** A default is a constant. What stands in here is
  the output of a step, known only at run time.

## Consequences

- A run started by an event opens a pull request whose last section is what the generator prints
  on the change's tree, which is the tree the description check reads.
- A worker that ignores `after` fails W-18. A third-party worker built against v1 before this
  change gains one obligation; `v1` may still move until a release uses it (ADR-0019).
- The manual start is unchanged: `tools/first_run.sh` still hands the section in, and the worker
  runs the command as well.
- A bundle can now declare an input optional. The command line asks only for the required ones.

## Where this promise ends

The section is as current as the tree the worker had. When `main` gains a record between the
clone and the branch's creation, the branch is made from the newer `main` and the section lists
the older register; the description check then fails, and the run's pipeline step does not
see it, because the check of the description runs on the pull request, not the branch. The
command's output is published as it is: a generator that prints something else than the
repository's check expects produces a description that fails, and the run does not judge it.
A command that hangs is ended at the worker's own bound, five minutes for the coding worker and
one for the script worker, and fails the assignment. The worker runs the command in its
workspace, but whether the command reaches the network is the execution environment's to
enforce, as for every command a worker runs (ADR-0007, `frame.allowed_hosts`). Nothing here
checks, at registration, that a reference to an optional input names a stand-in: a run that
lacks it and has none is refused before its first step, as a run that lacks any input is.
