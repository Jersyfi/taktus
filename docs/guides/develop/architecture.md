This guide is for someone who builds on Taktus: a process, a connector, a worker, or a model
provider. It assumes a clone of the repository and `uv`, the Python project tool. `make install`
sets up the environment; `uv run taktusctl --help` lists every command.

## The parts

Taktus is built in three layers.

- The **control plane** is Taktus itself, under `src/taktus/`. It decides what runs, admits
  every step against its limits, and records everything in the **ledger**, a chain of entries
  that cannot be changed unnoticed.
- The **execution plane** does the work: workers, connectors and models. Each is a separate
  program, reached over the network.
- The **contracts**, under `contracts/`, describe how the two talk. Each comes with a
  conformance suite that checks an implementation against it.

Inside the control plane, the code is divided by **component**: one package per part of the
domain, such as `process`, `run` or `governance`, under `src/taktus/components/`.

## Ports and adapters

A **port** is an interface the core defines for something outside it, under `src/taktus/ports/`.
An **adapter** implements a port for one technology or product, under `src/taktus/adapters/`.
The **composition root**, `src/taktus/composition/`, is the one place that builds adapters and
binds them to ports.

**The adapter obligation.** The core calls nothing outside it directly. Every outward access goes
through one of three adapter types:

- a **worker** carries out a task, such as running a command or a coding agent;
- a **connector** reaches a tool or a channel, such as a ticket system or a chat;
- a **model** answers a prompt.

A process names what it needs by **capability**, such as `repository.issues`, never by product.
Configuration maps a capability to an adapter. `make gate-arch` fails a product name or a
driver import in the core.

**The removal test.** Removing any one adapter must change quality or cost, and break no process.
Taktus runs this test on itself every week (`tools/removal_test.sh`).
