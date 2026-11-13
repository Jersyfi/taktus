---
name: development-scaffold
description: The artifacts a software project needs before AI can build it on its own — use cases, architecture decisions, a test strategy, a definition of done and a glossary. Use it when a development project starts, and to check that an existing one still keeps them.
---

# Development scaffold

A project that AI develops on its own needs a written answer to four questions before the
first change: what must be achieved, how it was decided, how it is tested, and when a change is
done. `scaffold.yaml` names the artifact that answers each. This skill says how to create and
keep them with the person who owns the project.

## The artifacts

- **Use cases** (`docs/usecases/`). One file per requirement. Each says what must be achieved,
  how it is verified, where it ends and what it rests on. Start from
  `templates/use-case.md`. A requirement without a verification condition is not finished.
- **Architecture decisions** (`docs/adr/`). One file per decision with an effect on the
  structure. Each states the context, the decision, the alternatives rejected and where its
  promise ends. Start from `templates/decision.md`. Write the decision before the code.
- **Test strategy** (`docs/test-strategy.md`). Which levels are tested, what each level
  proves, and what runs before a change merges. Start from `templates/test-strategy.md`.
- **Definition of done** (`docs/definition-of-done.md`). The list every change is held to.
  Start from `templates/definition-of-done.md`.
- **Glossary** (a page of the knowledge system). Every term the project uses, explained once.
  Start from `templates/glossary.md`.

## How to create them with the person

1. Check the project against this scaffold. Every artifact is named present, missing,
   unmaintained or unread.
2. For each missing artifact, propose the template as it is. Do not fill in decisions the
   person has not made: the structure is the scaffold's, the content is the person's.
3. Ask the person for the first entry of each, in their words: one use case, one decision, the
   levels they test at, the first line of the definition of done.
4. Repository artifacts arrive as one pull request. The person merges it.

## How to keep them

An artifact is unmaintained when the project changed for longer than its window while the
artifact did not. Name it to the person with how many days it is behind. Never rewrite it on
your own.
