# ADR-0100 — A task names a command the worker runs before the work

**Status:** accepted · extends the worker contract of ADR-0007 by one optional field of the task,
as ADR-0053 did for the command after the work, and check W-18 by its other half · issue #466

## Context

P-03 asks its coding agent to run the repository's own checks — the linter, the type checker,
the tests — in its workspace before the change is written to a branch. The workspace on the
installed instance could not run them. The worker's image carries a Python, git and the agent,
and nothing of any repository's toolchain. The agent tried to install the tools and failed at
the unit's egress proxy: the proxy admits the frame's hosts and the worker's service hosts
(ADR-0089), and no package index was among them.

So the agent wrote code it could not check. On 2026-10-16 the run for #256 was given back on a
red pipeline for the second time, for one linter finding (S603). The run had paid for its coding
step first. The research of 2026-10-14 names the gap as change 4
(`docs/research/2026-10-14-the-coding-worker-and-what-taktus-keeps.md` §7).

Three things decide where the fix belongs. The tools a repository checks with are the
repository's: the product must not ship one project's toolchain (ADR-0092). Installing them is a
fixed operation that needs no model: a model's turns spent on it cost money and may fail
differently each time. And the network a unit reaches is decided when the unit starts, for the
whole unit: a proxy cannot tell the agent's shell from another program in the same unit.

## Decision

### 1. The task may name a command before the work
The worker contract's `Task` gains an optional `before`: a `command`, as a program and its
arguments, and the `artifact` identifier its output is published under.

- The worker runs the command in its prepared workspace — for a coding worker the clone —
  as the assignment's first step, before any step of the work.
- The command runs without a shell. The worker gives it no credential.
- What it writes to its standard output and its error output becomes the named artifact, as
  `text/plain`, also when it fails, so that a failed setup can be read.
- A command that exits with anything but 0 fails the assignment, and the work does not start.
  For a coding worker no model has been called: the failure costs no money.
- What the command leaves in the workspace is part of the workspace the work starts from, not
  part of the work's change. A coding worker commits it into its baseline before the agent
  starts.
- A resumed assignment that continues in the workspace it left does not run the command again.
  One whose workspace is gone runs it again, and announces no artifact it announced before.
- The step reports its consumption like every step: for a coding worker, no tokens and no money.

Check **W-18** holds a worker to this half as well. It is one rule: the task's own commands,
around the work, run by the worker and never by a model. The suite runs the same work twice
with a command before it. One prints a value only that run knows, which must come back as the
named artifact, produced by the first step, with the work after it. The other exits with 1,
which must fail the assignment before any step of the work starts. All four workers pass it,
and each one's fault `W-18` now ignores both commands.

### 2. The hosts the command needs are hosts of the frame
The command reaches the network through the unit's proxy, as git does (#306). The hosts it needs
— a package index — are named in the step's `allowed_hosts`, by the bundle that names the
command. No separate list is added for the command. The proxy is configured once per unit and
cannot tell the command from the agent's shell; a list of hosts only the command may reach would
promise a separation the network does not hold. A host in the frame is a host the step may
reach, which is true of a package index the step installs from.

### 3. The coding worker's image carries generic tools, and caches under its state
The coding worker's image gains `uv`, a Python package manager, at one exact version, and
`make`. Both are generic: neither is this repository's. A repository's linters and test runners
are installed by its own command before the work, at the versions its lock file holds.

The command, and the agent after it, are given `XDG_CACHE_HOME` under the worker's state
(`<state>/cache`). A unit keeps its state on its claim across assignments (`deploy/k8s/README.md`
§7). The first assignment fetches what the lock file names; later ones find it in the cache. A
cache is a convention most package managers follow, and the worker names no tool by it.

### 4. P-03 uses it
P-03 version 13 has its implementing worker run `uv sync --all-extras --frozen` before the work,
published as `setup`. Its frame admits `pypi.org` and `files.pythonhosted.org`, the two hosts
this repository's lock file names. The acceptance criterion about the repository's checks names
the commands the setup makes available: `uv run ruff check .`, `uv run ruff format --check .`,
`uv run mypy` and `uv run pytest` on what the change touches.

## Alternatives

- **Tell the agent to install the tools.** It cannot reach a package index today. With the
  hosts in the frame it could, but each run would spend model turns on a fixed operation, and
  it may do it differently each time. A command needs no model.
- **Bake this repository's tools into the worker image.** Fast, and wrong: the product would
  ship one project's toolchain (ADR-0092), and the image's versions would drift from the lock
  file the pipeline installs from.
- **A list of hosts on the command, apart from the frame.** It would keep the frame narrower on
  paper. The unit's proxy admits one list for the whole unit, so the agent could reach those
  hosts all the same. A boundary that holds only in the bundle is the one ADR-0089 refuses.
- **The operator names the setup command for the worker** (`unitEnv`, ADR-0090). One worker
  serves several repositories and tenants; the command belongs to the repository, and so to its
  process, not to the deployment.
- **A new check W-19.** The rule is the same as W-18's: the task's own command, run by the
  worker, its output an artifact, its failure the assignment's. One check keeps every report's
  list of checks as it was.

## Consequences

- `contracts/worker/v1`: `Task.before` and `BeforeCommand`; README §3 and §7, CONFORMANCE.md,
  examples. Additive: a task without `before` is unchanged.
- `ports/worker.py`: `BeforeCommand`; the run passes it from the step's work to the assignment.
- The conformance suite gains two runs, `before-command` and `before-command-failing`, and the
  stream rule of W-18 its other half.
- The four workers run the command: both coding workers in their workspace, the script worker
  and the ML bench worker as their first step.
- The coding worker's image carries `uv` and `make`; a release rebuilds it.
- P-03 becomes version 13.
- An installation that runs P-03 on a cluster needs nothing new: the hosts are the frame's, and
  the proxy admits the frame's hosts. Port 443 must be among `execution.egress.ports`, as it is
  for the clone.

## Where this promise ends

The worker runs the command and reports what it wrote. Whether the workspace can then run the
repository's checks is the command's business: a command that succeeds and installs the wrong
thing is not detected here, and the agent finds out when it runs a check.

The command reaches what the frame's hosts reach, through the unit's proxy, on the proxy's
ports. On the execution kinds `process` and `endpoint` nothing enforces that: the command
reaches what the machine reaches, as every program a worker runs does (ADR-0053). The proxy
sees host names, not traffic: a package index in the frame is a host the agent's shell can reach
too, for the whole assignment, and can send anything the unit holds to.

The cache is as durable as the unit's state. Without a claim, every assignment fetches
everything again: about half a gigabyte for this repository, in about half a minute measured on
a laptop's connection. With a claim, a later assignment links what it needs from the cache, in a
few seconds. Several units sharing one claim share one cache; the package manager's own locking
is what keeps them apart.

The command is bounded at fifteen minutes in both coding workers and at one minute in the
script worker and the ML bench worker, and is ended there; the assignment then fails. A command that writes a secret it
found in the workspace into its output publishes it: the worker gives the command no credential,
but it does not inspect what the command prints.

The checks the agent runs are the repository's checks in the workspace, not the pipeline. A
check that needs a container engine, a cluster or a host outside the frame does not run there,
and the pipeline stays the verdict (P-03's autonomy statement).
