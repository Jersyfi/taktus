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
  `AF-01-dev-orchestration.md`, `UC-02` is `AF-02-it-operations.md`, `UC-03` is
  `AF-03-software-operations.md`.

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
the virtual agent business). `make usecases` prints where each is filed. `UC-15.2` is a
deployment and is described in `blueprints/finance/`.

## Numbers given after version 2

Numbered in conversation, in no version of the definition: `UC-1.8` a session with project
knowledge; `UC-7.4` the decision request; `UC-9.5` bottleneck and waiting analysis. Numbered by
the migration's fourth step, for the requirements the owner stated outside the definition, each the
next free number of its area: `UC-6.11` the owner-facing channel; `UC-6.12` the product finding;
`UC-13.6` readable documentation beyond the repository. Numbered when a task needed a requirement
no use case stated, the next free number of its area: `UC-4.14` a process starts on what happens
in a tool (#76, DEC-0124); `UC-1.9` a contribution from a person Taktus does not know is triaged
for the owner (#245, DEC-0175); `UC-4.15` a person changes a process in dialogue, and rolls it back (DEC-0186). `UC-4.19` a person takes over a running step and hands the result back (DEC-0195 W3, NTC-0223), the next free number of its area. `UC-1.11` a person's own agent reaches Taktus, with the rights of their role (DEC-0195 W5, NTC-0225), the next free number of its area. `UC-6.14` the work inside a step is seen as it happens, and shared by role (DEC-0195 W8, NTC-0229), the next free number of its area. `UC-10.4` a first rehearsed process in ten minutes, measured (DEC-0195 W4, NTC-0231), the next free number of its area. Numbered for the features of DEC-0190 built in concept mode (DEC-0222), each the next free number of its area: `UC-4.20` a human step and a fallback to a person name a role (F2, NTC-0237); `UC-7.8` one register of everything that acts for a tenant (F4, NTC-0238); `UC-6.15` what breaks if an adapter goes, and where a wrong result went (F5, NTC-0239); `UC-9.7` a process shows how it really runs (F6, NTC-0240). Numbered for the
software business the owner accepted as the second tenant (DEC-0199, NTC-0210), each the next
free number of its area: `UC-4.16` an expected run that does not happen is an incident;
`UC-4.17` deadlines and response limits are rules of the process; `UC-4.18` a change is held to
its evaluation cases, and drift is measured; `UC-6.13` signals against corridors; `UC-7.5`
corrections are counted, and a level falls by rule; `UC-7.6` an outward message is labelled,
checked and held; `UC-7.7` a step sees only the data of its case; `UC-8.12` a cap on open work
and a stop to repetition; `UC-9.6` introduced in stages, each opened on evidence. The
blueprint-level `UC-03` was numbered with them. Issue #402 had named its own future case
`AF-03`; that case, if it is needed, is `UC-04`.

## Numbers of the definition with no file of their own

- `UC-5.1`, coupled control, is part of **`UC-5.2`**, which holds both modes as one use case.
- `UC-5.4`, the connector interface, is carried by architecture: the adapter obligation
  (ADR-0003), the connector contract (ADR-0024, `contracts/connector/v1`) and its conformance
  suite, which is its verification.
- `UC-12.2`, the IT service chat, is a deployment and is described in `blueprints/it-operations/`.
- The definition's table of example domains under `UC-15.1` is `blueprints/README.md`.

Every other number of the definition, `UC-1.1` to `UC-15.5`, keeps its meaning.

## The migration of the definition

The definition was moved into `docs/vision/` and `docs/usecases/` in four steps, from 2026-09-29 to
2026-10-09, following a working file, `docs/usecases/MIGRATION.md`. As that file said of itself, it
was deleted when the fourth step was complete; the repository's history holds it, and records that
name it refer to that history. What each step asked the owner is DEC-0030, DEC-0069, DEC-0082 and
DEC-0087.
