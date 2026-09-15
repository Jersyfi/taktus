# ADR-0001 — Python as the single server-side language

**Status:** accepted · supersedes an earlier draft that put Go in the core and Python in a worker

## Context
An earlier draft argued: the core does state management and concurrency, not model work, so Go
belongs in the core and Python behind the worker contract.

The first half holds. The second does not, and the reason is ADR-0004. Once *method selection* is
the distinguishing feature of the product, the core reasons about models, trains them, evaluates
them and compares them. Model work is not the periphery — it is the brain of the product. Putting a
language boundary through the brain is a seam in the wrong place.

## Decision
**Python ≥ 3.13 for everything server-side**, including the ML bench. TypeScript for the web app.
JSON Schema for contracts and the shared kernel. There is deliberately no second server-side
language.

## Why Python carries the core
- The core's work is almost entirely I/O-bound: waiting on workers, APIs and the database,
  coordinating, persisting. `asyncio` carries thousands of concurrent runs. The GIL constrains
  CPU-bound work, which the core does not do.
- Compute-heavy work happens in workers, or in libraries that release the GIL.
- One language means one toolchain, one test environment, one dependency system. For a project of
  this scope built by one person with AI, that is the single largest reduction of risk in the whole
  plan.
- The ecosystem for classical ML, neural models, embeddings and evaluation is Python and cannot be
  replaced.

## What is given up, stated plainly
- **No single static binary.** Installation is `docker compose up` rather than a downloaded file.
  For a product that needs a database anyway, that is not a real loss.
- **Weaker compile-time guarantees than Go.** Compensated by `mypy --strict`, frozen Pydantic value
  objects, and `import-linter` contracts that enforce the architecture in CI (ADR-0003).
- **Memory and throughput under very high concurrency** are a known future limit. It will be
  measured, not guessed, and the roles split (ADR-0002) allows scaling the run executor
  horizontally before the language becomes the constraint.

## Alternatives
- **Go in the core, Python in a worker** — the earlier draft. Two toolchains for one person, and a
  boundary through the product's core reasoning.
- **Go only** — would mean reimplementing an ML ecosystem. Lost time, no architectural gain.
- **Rust** — best runtime properties, worst iteration speed for a solo project. The bottleneck here
  is development, not execution.

## Consequences
- The ML bench is no longer a language boundary; it is an ordinary module that runs as a worker for
  isolation and resource reasons, not for language reasons.
- Architecture enforcement moves from the compiler to the test suite. Those tests are therefore not
  optional and belong to `0.1.0`.
