---
name: analysis-scaffold
description: The artifacts an analysis needs before AI can carry it out on its own — the question, the data sources with their provenance, the method, the assumptions and the findings with what they rest on. Use it when an analysis starts, and to check that a running one still keeps them.
---

# Analysis scaffold

An analysis is only as good as what it can show it rests on. `scaffold.yaml` names the
artifacts that make each result traceable to its question, its data and its method. This skill
says how to create and keep them with the person who asked the question.

## The artifacts

- **Question** (`analysis/question.md`). What is to be found out, for whom, and which decision
  it serves. Start from `templates/question.md`.
- **Data sources** (`analysis/sources.md`). Every source with where it comes from, when it was
  read and who may see it. Start from `templates/sources.md`.
- **Method** (`analysis/method.md`). How the question is answered, and why this method over the
  others. Start from `templates/method.md`.
- **Findings** (`analysis/findings/`). One file per finding, each naming the sources and the
  step of the method it rests on. Start from `templates/finding.md`.
- **Assumptions** (a page of the knowledge system). What the analysis takes as given, so that a
  reader can challenge it. Start from `templates/assumptions.md`.

## How to create them with the person

1. Check the project against this scaffold.
2. For each missing artifact, propose the template as it is. The question and the decision it
   serves are the person's; do not phrase them on their behalf.
3. Repository artifacts arrive as one pull request. The person merges it.

## How to keep them

The sources go stale first. Name them to the person when the analysis moved on and the list of
sources did not.
