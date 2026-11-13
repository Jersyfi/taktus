---
name: process-automation-scaffold
description: The artifacts an undertaking needs before a process of it can run without a person — the process description, the takeover instructions, the anchors that stay with a person, the evaluation cases and the list of systems it touches. Use it when a process is to be automated, and to check that an automated one still keeps them.
---

# Process automation scaffold

A process that runs on its own must still be one a person can take over. `scaffold.yaml` names
the artifacts that make that true. This skill says how to create and keep them with the person
who owns the process.

## The artifacts

- **Process description** (`process/description.md`). The goal, the steps in order, and for
  each step its method and why. Start from `templates/process-description.md`.
- **Takeover instructions** (`process/takeover.md`). How a person runs the process without
  Taktus, step by step. Start from `templates/takeover.md`. A process without them does not run
  on its own.
- **Anchors** (`process/anchors.md`). The acts that stay with a person at every level of
  autonomy: legally binding acts and acts that set direction. Start from `templates/anchors.md`.
- **Evaluation cases** (`process/cases/`). Inputs with the result the process must reach, so
  that a change can be held to them. Start from `templates/case.md`.
- **Systems** (a page of the knowledge system). Every system the process reads or writes, by
  the capability it needs, never by product. Start from `templates/systems.md`.

## How to create them with the person

1. Check the project against this scaffold.
2. For each missing artifact, propose the template as it is. The person states the goal, the
   anchors and the first cases; do not invent them.
3. Repository artifacts arrive as one pull request. The person merges it.

## How to keep them

The takeover instructions change whenever a step changes. Name them to the person when the
process moved on and they did not.
