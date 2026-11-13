# ADR-0308 — A scaffold is checked and furnished from a process and from the command line, and SC-01 evaluates it

**Status:** accepted · extends ADR-0307 (method scaffolds), ADR-0162 (the skill lifecycle) · UC-13.2

## Context

ADR-0307 built the check and the furnishing of a project against its method scaffold. It left two
gaps, and said so.

- **No surface.** Nothing could ask for a check or a furnishing. They were reached through the
  application service only.
- **No way to production.** A skill reaches production through rounds on the evaluation cases of
  the processes that use it (ADR-0162 §3). No process used a shipped scaffold, so every scaffold
  stayed a draft on an instance. A draft can be checked against, and it cannot furnish.

## Decision

### 1. The loopback connector serves `orchestrator.scaffolds`

A process reaches the instance through the loopback connector, as the guides do (ADR-0066). The
capability `orchestrator.scaffolds` has two operations.

| Operation | Effect | Input | Output |
|---|---|---|---|
| `orchestrator.scaffolds.check` | `read` | `scaffold`, `branch`, optional `place` of two names | the check: `scaffold`, `stage`, `commit`, `newest`, `findings`, and `missing` and `unmaintained`, the titles of those artifacts |
| `orchestrator.scaffolds.furnish` | `write`, `marked` | the same | what was furnished: `created`, `kept`, `branch`, `pull_request`, and the check |

The instance answers through the protocol `Scaffolds`, which the composition root implements over
`InstanceScaffolds` (ADR-0307 §6). The repository and the knowledge system are resolved by
capability. The call's run, step and credentials are the ones the writes act under. Every write
is keyed from the run, so furnishing is `marked`: a repeat finds the branch, the pull request and
the pages and creates nothing twice. A furnishing that created nothing is reported `replayed`. A
rehearsal does not call it (ADR-0030).

### 2. `taktusctl scaffold check|furnish`

`taktusctl scaffold check NAME --branch B [--shelf S --book K]` prints the check as JSON. It exits
1 where an artifact is missing or unmaintained, so that a repository's CI can run it.
`taktusctl scaffold furnish NAME …` furnishes the project and prints what it created. Both use the
connectors the instance is configured with. A scaffold that is not in production is refused for
furnishing, with exit code 1.

### 3. SC-01 uses the development scaffold and carries evaluation cases

The blueprint `method-scaffolds` holds one process, SC-01 *Check a development project*. It has two
steps.

| Step | Method | Exactness | Reason | Rejected | Fallback |
|---|---|---|---|---|---|
| `check` | `rule` (`orchestrator.scaffolds.check`) | `sourced` | the state of each artifact is a rule over two dates (ADR-0307 §7) | `llm` — whether a file is there is not judgement | a person checks by hand from `scaffold.yaml` |
| `advise` | `llm`, with the skill `development-scaffold` | `free` | what to ask the person first, per missing artifact, is language | `rule` — no rule phrases a question for a person | a person reads the check |

The step `advise` names the scaffold in `work.skills`. The scaffold's rounds therefore run on
SC-01's evaluation cases, both sides as rehearsals, and its approval follows SC-01's autonomy level:
a person approves at level 2. Once in production, the scaffold furnishes. SC-01 itself writes
nothing outside: furnishing stays a separate act a person asks for.

## Alternatives

- **An HTTP route.** Not taken now: the loopback operation serves a process and the command line
  serves a person; the web app has no page for scaffolds yet.
- **Furnishing as a third step of SC-01.** Rejected: SC-01 runs on a schedule or by request; a
  pull request into the organisation's repository is an act the person asks for.
- **Production without rounds for a curated scaffold.** Rejected by UC-13.2 §2: the same
  evaluations and approval as a learned skill.

## Where this promise ends

SC-01 evaluates the development scaffold only. The process-automation and analysis scaffolds reach
production only when a process of the organisation names them in `work.skills` and carries cases.
SC-01's cases hold the advice to naming what is missing; they do not judge whether the advice is
good beyond the scorer's rule. The command line needs the instance's state and its configured
connectors; on an instance without a repository connector every repository artifact is `unread`.
No page of the web app shows a check.
