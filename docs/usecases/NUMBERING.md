# Use case numbers

A use case keeps its number for good. This file says how numbers are given, and where a number
used somewhere else — in the original project definition, in an earlier proposal, in a
conversation — points in this repository. It is permanent: it stays when the migration of the
definition is complete, so that an old reference stays findable.

## How a number is given

- **`UC-<area>.<case>`.** The area is the epic of the original project definition: 1 command
  and interaction, 4 the process engine, 6 reporting, 7 governance, 8 the model platform, and so
  on. The area is not the component. `UC-6.3` is a reporting case by origin and is filed under
  `process/`, because the takeover instructions are part of the process version (ADR-0029).
- **What the repository wrote down first wins.** A number that appears in this repository keeps
  the meaning it has here, whatever the definition or a conversation gave it.
- **A number the definition used and the repository did not is kept** with the definition's
  meaning.
- **A new use case takes the next free number of its area.** A number is never reused, not
  even after its use case is retired; a retired use case stays as a file with state `retired`
  and a pointer to what replaced it.
- **Blueprint-level cases** — one whole business function run by Taktus — are numbered
  `UC-<nn>` with two digits and no dot, and live with their blueprint: `UC-01` is
  `AF-01-dev-orchestration.md`, `UC-02` is `AF-02-it-operations.md`.

## Where the definition and the repository disagree

The definition exists in versions. The one the repository is checked against is **version 2**,
epics E1 to E15, market chapter dated September 2026. An earlier version of 2026-09-01 had epics
E1 to E13 only; nothing it numbered was renumbered by version 2. A few cases were numbered later
still, in conversation, and are listed at the end.

| Used elsewhere | Meant there | In this repository |
|---|---|---|
| `UC-4.5` (definition) | monitoring, alerting and self-healing | **`UC-4.6`**, self-healing within the frame. The repository numbered the two cases the other way round (`docs/architecture/control-plane.md` §5.2) and wins. Quality monitoring of results is `UC-4.10` |
| `UC-4.6` (definition) | escalation with a complete situation package | **`UC-4.5`**, a step fails: halt or escalate at the boundary. The situation package is part of its escalation |
| `UC-7.2` (definition) | escalation and intervention, including the emergency stop | **`UC-7.2`** keeps the emergency stop; the escalation is `UC-4.5` |
| `UC-4.8` (an earlier proposal) | working out how a step becomes exact | **`UC-4.13`**, where the repository wrote it |
| `UC-4.7`, `UC-4.8`, `UC-4.9` | each used for two different cases in different conversations | **retired, never assigned.** A reference to one of them cannot be resolved without the conversation it came from, so none of the three is given to anything. The one meaning known to the repository is the line above |

## Numbers the repository wrote first

Kept as they are, whatever the definition said: `UC-4.5`, `UC-4.6`, `UC-4.10` deviation
detection, `UC-4.11` error window and impact analysis, `UC-4.12` remediation plan, `UC-4.13`
working out how a step becomes exact, `UC-6.8` incident and incident report, `UC-6.9` the
exactness statement, `UC-7.2` emergency stop — and the blueprint-level `UC-01` and `UC-02`.

## Numbers of version 2 not in the earlier version

Kept with the meaning version 2 gives them: `UC-1.7` channel identity — every command belongs to
one Taktus identity; `UC-5.8` connecting observability and evaluation platforms, optional;
`UC-6.7` the bus-factor index; `UC-8.11` role-based agents — one agent, many departments;
`UC-14.1` the worker interface, `UC-14.2` the skill lifecycle, `UC-14.3` the skill hub (epic E14,
the execution layer: workers, skills and the learning loop); `UC-15.1` domain blueprints,
`UC-15.2` the finance reference domain under legal anchors, `UC-15.3` partner interfaces,
`UC-15.4` end-to-end processes across domains, `UC-15.5` the responsibility anchor (epic E15,
the virtual agent business). Where each is filed is `MIGRATION.md`.

## Numbers given after version 2

Numbered in conversation, in no version of the definition, known to the repository by the titles
`MIGRATION.md` gives them: `UC-1.8` a session with project knowledge (the roadmap's `0.3.0` names
it); `UC-7.4` the decision request (ADR-0008 and ADR-0017 carry it); `UC-9.5` bottleneck and
waiting analysis (ADR-0015 carries it). Their text arrives with the step of the migration that
files them.

Every other number of the definition, `UC-1.1` to `UC-15.5`, keeps its meaning.
