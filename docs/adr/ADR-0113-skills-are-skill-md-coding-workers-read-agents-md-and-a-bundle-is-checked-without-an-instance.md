# ADR-0113 — Skills are SKILL.md, coding workers read AGENTS.md, and a bundle is checked without an instance

**Status:** accepted · extends ADR-0011 (process bundles) · issue #407, DEC-0195 (W6), NTC-0216

## Context

DEC-0195 took ten lessons from a review of a development environment for agents. Lesson W6 says
that Taktus should use the formats its field agreed on instead of its own. Principle 13 asks for
the same: freedom instead of lock-in. Three places lacked such a format.

- **Skills.** A skill is a reusable, versioned piece of know-how that a model or a worker uses
  for one kind of task (UC-14.2). The project definition named an open format, `SKILL.md`, as
  the contract for skills. No ADR chose it, and `docs/vision/history.md` names that gap. The
  skill lifecycle (UC-14.2) and the skill hub (UC-14.3) wait for it.
- **A repository's rules for coding agents.** The coding workers briefed their agent with the
  task alone. The repository's rules reached the agent only where the agent read a file named
  after its own product. The first coding worker's agent reads `CLAUDE.md`. Another agent reads
  another file. A rule written for one product was lost on the other. The open convention for
  this file is `AGENTS.md`, at the root of the repository.
- **Checking a bundle.** A bundle was checked only by registering it, which needs an instance,
  its database and an identity. A repository that holds bundles had no way to check them in its
  own CI.

The coding agent re-reads its whole context at every call. On Taktus's instance, about 120,000
tokens were read per call, and the repository's brief is part of them (#511). Whatever the
workers add to the brief is paid for at every call.

## Decision

### 1. A skill is a directory with a `SKILL.md`

A skill is a directory named after the skill. It holds a file `SKILL.md`: YAML front matter,
then the instructions in Markdown. Other files in the directory belong to the skill: scripts,
references, templates. The instructions name them where they are needed.

The front matter carries two fields that every skill must have, as the open format defines them.

- **`name`**: 1 to 64 characters, lowercase letters, digits and hyphens. It does not start or
  end with a hyphen and has no two hyphens in a row. It equals the directory's name.
- **`description`**: 1 to 1,024 characters. It says what the skill does and when to use it.

Further fields of the open format are kept as they are. One of them is not honoured:
`allowed-tools`. The frame of an assignment alone decides which tools a step may use
(`contracts/worker/v1`). No skill widens the frame.

Taktus adds no field to the file. What Taktus knows about a skill beyond the file — its
version, its origin, its stage in the lifecycle, its evaluations — is kept beside it in the
catalogue (UC-14.2). A skill exported is therefore the open format, unchanged (UC-14.3).

### 2. Where a skill lives, and how a step names it

A skill lives in a bundle, as ADR-0011 says, under `skills/<name>/SKILL.md`, beside the
bundle's processes. A blueprint keeps its skills under `blueprints/<id>/skills/`. A skill is
versioned with its bundle.

A step that uses a skill names it in its `work`, under `skills`, by the skill's name:

```yaml
work:
  skills: [triage-an-issue]
```

The name is the skill's, never a product's. The step still reaches its worker or its model by
capability (ADR-0003). The run hands the skill's files to whichever adapter serves the step. The
adapter makes them available to its agent the way that agent reads skills. An agent that knows
no skills receives the instructions in its brief. A skill names no product, no worker and no
model. Know-how that works with one product alone is adapter code, not a skill.

A skill never changes what may produce a step's result. A skill used by an `exact` step guides
the method, and the step's exactness class still bounds the result (ADR-0014, UC-14.2).

### 3. The coding workers hand the agent the repository's `AGENTS.md`

`AGENTS.md` at the root of the target repository is the file of its rules for coding agents.
Both coding workers read it in the workspace and put it into the agent's brief. It comes after
the worker's own lines and before the task, between two lines that name the file.

- **The worker's lines win.** Where the rules conflict with what the worker asks — work in
  this directory only, do not use git — the worker's lines win, and the brief says so. The
  frame and the contract are not the repository's to change.
- **Once per session.** A fresh assignment carries the rules. A resumed one does not, because
  its session holds them already. A second copy would be paid for at every call.
- **Bounded.** The brief carries at most 32,000 characters of the file. A longer file is cut
  there, with a line saying that the rest is in the file.
- **Inside the workspace only.** A link that leads out of the workspace is not followed. The
  repository is not the worker's, and a link to a file of the worker — a credential's — must
  not reach the agent's context.
- **No file at all, or an empty one**: the brief is what it was before.

**How `AGENTS.md` relates to a file named after one agent.** `AGENTS.md` is the one file every
coding worker hands over, so no worker depends on one product's file name. A file named after
an agent — `CLAUDE.md` for the first coding worker's agent — belongs to the repository and is
written for that agent. Nothing in Taktus reads it. An agent that reads its own file by itself
still does: its worker does not stop it. Where an agent would read `AGENTS.md` by itself as
well, its worker keeps the rules from arriving twice.

- The first coding worker's agent reads its own file and resolves a line `@AGENTS.md` in it.
  Where that line is there, the brief leaves `AGENTS.md` out.
- The second coding worker's agent reads `AGENTS.md` by itself. Its worker turns that reading
  off and hands the file over in the brief, as the first does.

A repository is best served by keeping its rules in `AGENTS.md`. A file for one agent, where one
is needed, imports or points to it. Then the rules exist once, every agent reads the same, and
replacing the agent changes nothing (principle 13).

### 4. `taktusctl bundle check` checks a bundle without an instance

`taktusctl bundle check PATH…` holds each bundle to the rules registration holds it to. It calls
the code registration calls, `parse_bundle`: the shape of the bundle, the rules of every step,
the graph, and the exactness statement. There is no second validator. The command needs no
instance, no database, no login and no network. It stores nothing and records nothing.

A path is a bundle file or a directory. Below a directory every YAML file is checked, except one
whose top-level `kind` says it is no process and that lists no steps, such as a blueprint. A
file named itself is always checked. The exit code is `0` when every bundle would register, `1`
when one would be refused, and `2` when a file cannot be read or no bundle was found.
`examples/README.md` documents a CI job for a repository that holds bundles.

### 5. This repository's `AGENTS.md` points to `CLAUDE.md`

This repository gains an `AGENTS.md`. It carries no rule of its own. It says that the doctrine is
`CLAUDE.md`, that it binds every agent and every person, and that it must be read whole. The
doctrine stays in `CLAUDE.md`, unchanged and unshortened. `CLAUDE.md` §9 states the rule that a
rule goes there and never into `AGENTS.md`.

The doctrine keeps its file because more than a hundred files name it, the gates read it (`tools/check_vision.py`
reads its §5), and the migrations name it in their texts, which are never changed. A pointer
keeps the doctrine whole and in one place. Each agent reads it once: the first coding worker's
agent reads `CLAUDE.md` by itself and is handed the pointer of a few lines; the second is handed
the pointer and reads `CLAUDE.md` through it. Moving the doctrine into `AGENTS.md` would be a
change of its own, made whole in one pull request (NTC-0216).

## Alternatives

- **A skill format of Taktus's own.** Rejected: principle 13. A skill written for Taktus would
  not run elsewhere, and a skill written elsewhere would need converting.
- **Taktus's fields in the skill's front matter.** Rejected: the exported skill would carry
  fields no other reader knows, and the version would live in two places.
- **Each worker reading its agent's own file and handing it over.** Rejected: every worker would
  depend on one product's file name, and a repository would keep one copy of its rules per
  product.
- **Relying on each agent to read `AGENTS.md` by itself.** Rejected: whether an agent reads it
  depends on the product and its version, and no test of the worker could show it.
- **Handing over the rules at every resume as well.** Rejected: the session holds them, and the
  copy is paid for at every call (#511).
- **A validator of its own for `bundle check`.** Rejected: two validators drift apart, and a
  bundle that passes one would be refused by the other.
- **Moving the doctrine into `AGENTS.md` now.** Rejected for this change: see §5.

## Where this promise ends

The skill format is chosen, and nothing loads, checks, hands over or versions a skill yet. A
step's `work.skills` is read by nothing until the skill lifecycle of `0.6.0` is built (UC-14.2),
and `bundle check` does not look at skills. The workers hand over the root's `AGENTS.md` only.
A file of the same name in a subdirectory is not handed over, though the agent may read it like
any other file. The worker hands the rules over and cannot make the agent follow them. Where a
repository has no `CLAUDE.md`, the first coding worker's agent may read `AGENTS.md` by itself
as well, at the version it is pinned to; the rules then reach it twice. That costs what the file
holds at every call and changes nothing in what the agent is told; #511 measures the brief. The
brief carries 32,000 characters of the file at most. `bundle check` does not make the three
refusals of registration that need an instance: a credential that administers the instance's
platform (ADR-0025), a raise of an autonomy level (ADR-0039), and a version registered before
with another content. It holds a step's `work` to being a mapping and no further, so a bundle
that passes can still fail when it runs, for example on a capability no adapter serves.
