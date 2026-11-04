# ADR-0180 — Every process version carries its takeover instructions, and a trial of them is kept with it

**Status:** accepted · extends ADR-0013 B (a person can take over any process), ADR-0029 (the instructions are part of the process version), ADR-0128 (taking over a running step) and ADR-0137 (a stage opens only on current instructions) · issues #627, #404; UC-6.3, UC-4.19, UC-9.6

## Context

ADR-0013 B promises that a person can run any process without Taktus. UC-6.3 makes the promise
checkable: every process version carries instructions for a person, and a trial in which a
person ran the process from them alone is kept with the version. Until now no version carried
instructions. The blueprints' READMEs described some processes by hand, outside any version.
The skill part existed on its own: `taktusctl skill takeover` lists each step's skills at their
version in production (ADR-0162). The stages of ADR-0137 therefore could not open, because their
port answered that no process has instructions.

Three questions were open. Where the instructions live, so that they cannot drift from the
steps. What registration can check, without judging prose. Where a trial is kept, and what the
automated takeover test of `0.5.0` is.

## Decision

### 1. The instructions are a section of the bundle

A bundle carries `takeover`. It has two parts:

- `sequence`: the process as a whole, in a person's words: when it runs, in what order, and who
  starts it.
- `steps`: one entry per step, keyed by the step's identifier. Each entry names `system` (the
  system to act in), `do` (what to do there), `expertise` (what the person needs to know),
  `credentials` (each by its `parameter` and `where` an authorised person finds it, possibly
  none) and `done` (how to tell that the step is done).

The sixth element, **the skills the step uses by version**, is not written. It is derived when
the instructions are read: each skill the step names under `work.skills`, at its version in
production, with its instructions (ADR-0162 §3). A written list could only drift from the
step.

The section is part of the version's content. Changing it needs a new version, like any other
change (#377).

### 2. What registration refuses

Registration refuses, with every finding named:

- a bundle without `takeover`;
- an entry for a step the version does not have, and a step without an entry;
- an entry that leaves out one of its five written elements, or gives an empty text;
- a step whose work names a credential literally (`credentials: [{name: ...}]`) that its entry
  does not name as a `parameter`. A credential given by a reference is known only when a run
  resolves it; the entry names the parameter a person uses and says where to find it;
- a text that names a Taktus identifier a person could not look up without Taktus: a template
  reference (`$input`, `$from`, `$run`, `${…}`), a record of the repository's register (ADR, DEC,
  NTC, NEED, UC numbers), or an identifier an instance gives its records (`run_0001`).

This is how "the instructions belong to the version" is held: they are inside it, they cover
its steps exactly, and a credential a step gains without its entry naming it does not register.
`taktusctl bundle check` holds a bundle to the same rules without an instance (ADR-0113 §4).

A plan draft from a process model (ADR-0168) asks for the instructions of each step as an open
question, so that the bundle it becomes registers. A version written back as a bundle for a
rollback (UC-4.15) or a move (ADR-0114) carries the instructions of the version it came from.

### 3. A trial is kept with the version

A person records a trial with `taktusctl takeover trial <process>` or
`POST /processes/{process}/takeover/trials`: the role that ran it, whether they could run the
process from the instructions alone, and what was missing. The record names the version that
was active then and when it was recorded. It is stored in `takeover_trial` (migration `0098`)
and recorded as the ledger entry `takeover.trial`, outcome `passed` or `failed`, whose actor is
the person who recorded it, for the audit only. The record names a role, never a person, and no
figure is computed from trials per person (principle 14).

A process whose active version runs at level 3 or 4 and has no passed trial on that version is
**untried**. The process read of the HTTP surface and the web app's process page say so beside
the level.

`GET /processes/{id}/takeover` and `taktusctl takeover show <process>` give the instructions
of the active version, with the derived skills, its trials and whether it is untried.

### 4. A take-over hands the person the step's instructions

The state a person receives when they take over a running step (ADR-0128 §3) carries the
step's entry of the version's instructions. A person who takes a step over has what they need
to do it by hand.

### 5. The automated takeover test

The automated takeover test is a test of the repository that runs a process at level 3 the way a
person would, through the take-over of ADR-0128 (`tests/composition/test_takeover_test.py`). A
person takes over its worker step while it runs and receives the state with the step's
instructions. The test does what the instructions' `do` names — it runs the command they name
in a shell, read from the instructions, not from the step's work — and hands the output back.
The rule after the step checks the person's value as it would the worker's, the run finishes,
the trial is recorded, and the version is no longer untried. A second test reads every bundle
under `examples/` and `blueprints/` and finds, for every step, all six elements and no
identifier a person could not look up.

For the step after a hand-back to read the person's value, a hand-back now records its result
as the step's result: `{ $from: <step> }` resolves to what the person handed back, as it does to
a rule's value. Before, it resolved to the step's list of artifacts, and the result's artifact
was named by the take-over, which no bundle can know.

### 6. A stage opens on instructions that exist

ADR-0137's port `TakeoverInstructions` is answered from the active version: a process lacks
instructions when it has no active version, or when its active version was stored before this
decision and carries none.

## Alternatives

- **Instructions under each step.** A step entry could carry its own instructions. Then the
  section could no longer state the process as a whole, and the step mixes what Taktus does
  with what a person does. Rejected.
- **Instructions as a document beside the version.** A separate document can be edited without
  a new version, and then describes a version nobody runs. Rejected: ADR-0029 files them in the
  version.
- **Registration compares a changed step's instructions with the replaced version's.** A step
  moved from a language model to a rule (ADR-0114) changes what Taktus does, not what a person
  does by hand. Refusing every unchanged entry beside a changed step would refuse the right
  instructions. Rejected.
- **The trial as a ledger entry alone.** The ledger holds no content (ADR-0135), and what was
  missing is content. Rejected.

## Consequences

- `process`: `domain/model/takeover.py`, `ProcessVersion.takeover`, registration's findings,
  `application/service/takeover.py` for trials; the bundle written back carries the section.
- Migration `0098` adds `process_version.takeover` and the table `takeover_trial`.
- `LedgerEntry.json` gains the kind `takeover.trial`.
- Every bundle under `examples/` and `blueprints/` carries `takeover` and a new version.
- The composition answers the stages' port and adds the instructions to a take-over's state.
- `taktusctl takeover show|trial`, `GET /processes/{id}/takeover`,
  `POST /processes/{id}/takeover/trials`; the web app shows *untried* beside the level.

## Where this promise ends

Registration checks the instructions' shape, their cover of the steps, the credentials and the
identifiers. It does not check that the prose is right: a person who writes wrong instructions
registers them, and only a trial finds it. A version stored before this decision is read as it
is, carries no instructions, and keeps its stage closed until a version with instructions is
registered. A rollback to such a version is refused until the instructions are written. A
credential given by a reference is checked by nobody before a run. The skills are derived at
the moment the instructions are read, so a skill produced after a trial changes what a person
reads without changing the version; the trial names the version, not the skills' versions. The
automated takeover test exercises one worker step of a test's own process by hand; it cannot
judge whether a person could do every step of every process. That stays the trial a person records.
A trial records what the person says; Taktus does not observe the person. Where else a level is
shown — reports, the chat, the register — *untried* is not said yet.
