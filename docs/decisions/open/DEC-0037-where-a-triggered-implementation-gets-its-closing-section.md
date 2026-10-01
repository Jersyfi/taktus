# DEC-0037 — Where a triggered implementation gets its closing section

**Category:** NON-BLOCKING
**Raised in:** PR_LINK, which moves the closing section out of the model's hands (issue #34)
**Issue:** [#49](https://github.com/Jersyfi/taktus/issues/49)
**Needed by:** 2026-11-15
**Provisional answer:** Option C for now: the command that starts the process by hand, `tools/first_run.sh`, generates the section and hands it to the run as an input. Marked in the bundle's `closing_section` input and in `blueprints/dev-orchestration/README.md`.

## 1. What this is about

When Taktus implements an issue, it opens a pull request. The description of every pull request
in this repository ends with a section that lists what is needed from you. That section is
**generated**: a small program reads the open decision requests and needs requests and prints
the list. The repository's checks compare the section with what the program prints, exactly.

In the first live run a language model was asked to copy that section into the description.
Copying is a fixed operation, and asking a model for it puts a result that must be exact behind
a method that varies. The run of 2026-09-23 lost four attempts on parts of the description that
were fixed text asked of the model.

This pull request takes the copy away from the model: the run appends the section itself, as
fixed text, from an input it is given. Today that input comes from the command a person uses to
start the process by hand, which runs the program on the repository. Once the process is started
automatically — by a schedule or by an event, which is the next milestone — nobody runs that
command, and the input has to come from somewhere else.

## 2. Why you are being asked

Entry M3.13 of `docs/decisions/anchors.taktus.md`: "Choosing a method within an exactness class,
where the class admits more than one." The section must be exactly what the program prints; the
question is which method produces it inside a run, and there are three that can.

## 3. What you must decide

Where an automatically started implementation run gets the generated closing section of its pull
request description.

## 4. What you need to know to decide

- **The process.** Implementation (P-03) reads an issue, has a coding worker change the code in a
  workspace of its own, puts the change on a branch, waits for the checks, and opens the pull
  request. The worker runs commands in its workspace; that is what it is for.
- **Which list is right.** The checks compare the section with what the program prints on the
  branch of the pull request, not on the main line. A list generated from the branch is
  therefore exactly the one the checks want.
- **What the repository already decided.** The list is not stored in any file, because a stored
  list conflicted between every two pull requests (DEC-0026). A way that stores it again reverses
  part of that decision.
- **A read of a file.** The repository connector can now read a file of the repository at a
  branch (`repository.files.read`). It cannot run the program.

## 5. Options

### Option A — the worker runs the program after its change (recommended)

- **Meaning:** the bundle names a command; after the coding agent is done, the worker runs it in
  its workspace — the branch as the pull request will carry it — and publishes what it printed as
  an artifact of its own. The run appends that artifact as fixed text.
- **Consequence:** the section is exactly what the checks will compare, generated on the very
  tree they check. The worker runs a named command, which is what it already does; no model is
  involved.
- **Effort:** about a day: the worker contract's task gains an optional command after the work,
  the coding worker runs it, the bundle names it.
- **Reversibility:** cheap.
- **Why recommended:** it is the only option whose source is the branch the checks read, and it
  stores nothing.

### Option B — a stored copy read at a branch

- **Meaning:** the section is written into a file of the repository again, and the run reads it
  with the new read operation.
- **Consequence:** it reverses part of DEC-0026: two pull requests that change the register
  conflict on that file again.
- **Effort:** half a day.
- **Reversibility:** cheap to build, and it reintroduces the conflict for as long as it stands.

### Option C — whoever starts the run supplies it

- **Meaning:** the input stays an input; an automatic start has to compute it before starting
  the run, as the manual command does today.
- **Consequence:** the scheduler needs a copy of the repository and the program to start one
  process; every automatic start of P-03 carries a special case.
- **Effort:** a day, in the scheduler.
- **Reversibility:** cheap.

## 6. What is blocked

Nothing today: the process is started by hand, and the manual command supplies the section. The
answer is needed before P-03 is started automatically, which is milestone `0.2.0`; without one by
2026-11-15, the provisional answer holds and an automatic start of P-03 cannot open a pull
request whose checks pass.

## 7. How to answer

"DEC-0037: Option A.", "DEC-0037: Option B." or "DEC-0037: Option C." in the issue. A free-text
answer is read back as an interpretation and confirmed before it is acted on.
