# ADR-0101 — A rule titles a pull request in the Conventional Commits form

**Status:** accepted · builds on ADR-0014 and ADR-0095 · issue #472

## Context
A pull request here is squash-merged. Its title becomes the commit on `main`. That commit
follows Conventional Commits (CLAUDE.md §9): a type such as `feat` or `fix`, an optional scope
in parentheses, a colon, and a summary.

P-03 titled its pull request with the issue's title and the issue's number. An issue's title is
a sentence. So #463 and #470 reached `main` as "A pull request P-03 opens repeats its sections …"
and "make gate-adrs fails a reference …", without a type. Nothing checked a title, whoever wrote
it.

Which type a change has is partly a fact and partly a judgement. A change that touches only
documentation is `docs`, and a label a person sets is a statement. Whether code adds a capability
or corrects one is what the coding worker knows best. A worker is a variable method, and a title
step is `exact`: a variable method may propose such a value, never produce it (ADR-0014).

## Decision

### 1. A rule composes the title
The run gains a rule kind, `commit_title`. It takes a sentence, a number and a list of allowed
types. It takes the type from the first source that gives one:

1. the sentence itself, where it is already in the form with an allowed type;
2. a label that the bundle's `label_pattern` matches, its group `type`;
3. the files changed, where every one matches the pattern of an entry of `by_files`;
4. a proposal, a text in which the bundle's `proposed` pattern is searched, its groups `type`
   and `scope`.

A type outside the allowed list counts as none. The summary is the sentence, its first letter
lower-cased unless its first word is an abbreviation. The result is the title
`<type>(<scope>): <summary> (#<number>)`, with the type, the scope and the source. No type from
any source fails the step, and so do two labels that name different types. The rule is
deterministic and admissible for `exact`. It names no repository: types, patterns and files'
rules are the bundle's.

### 2. P-03 asks its worker for a proposal and checks the title before it opens
P-03, version 17, titles its pull request with that rule. This repository's bundle names its
types, the label `type:<type>`, the files under `docs/` as `docs` and those under `tests/` as
`test`. The worker's summary proposes the type in an HTML comment on its first line,
`<!-- commit-type: <type>(<scope>) -->`, which a reader of the description does not see. A
`check` step then holds the title to the form, with the issue's number. A title that fails it is
not opened, and the run escalates.

### 3. The repository checks every title
`tools/check_decisions.py --pr-title` fails a title without the form, for every author,
dependency bots included. The host's own title for a revert, `Revert "<a title in the form>"`,
passes, as the guard on a red `main` expects it (`tools/ci_watch.py`). The workflow
`description` passes the title from the event, as it passes the description. A run of P-03
cannot change a workflow, so a person wires that line.

## Alternatives
- **A template with a fixed type.** Every change would be `feat`, and the history would say so
  falsely.
- **The worker writes the title.** A title produced by a variable method is not `exact`, and
  nothing would hold it to the repository's types.
- **A model step that classifies the change.** It costs a call. It judges from less than the
  worker, which made the change.
- **The issue's form gains a type field.** Every author of an issue would have to know the
  convention. A label `type:<type>` serves where a person wants to decide.
- **Composition from the existing rules.** Choosing the first of four sources, and deciding that
  every file matches, are not expressible with `template`, `extract` and `check` without
  encoding order into the texts.

## Consequences
- The run's rules gain `commit_title` (`examples/README.md`).
- P-03 has twenty-nine steps. Its takeover by hand titles the pull request the same way.
- The fake coding agents propose `feat`, so the integration tests open a titled pull request.
- `docs/process/README.md` lists the labels `type:<type>`.

## Where this promise ends
The rule guarantees the form, not the fitness of the type. A proposal the worker got wrong
passes as long as it is an allowed type. So does a label a person set wrongly. The files decide
only where every one is documentation or every one a test, in this bundle. A change of code and
its documentation together is left to a label or to the proposal.

The summary is the issue's sentence. Lower-casing its first letter reads a capital and more
capitals or digits as an abbreviation; a name in capitals at the start, such as "Python", is
lower-cased. A sentence longer than a commit summary should be is not shortened.

The repository's check sees the form of a title. It does not see whether the type fits the
change. It runs only where the workflow passes the title.
