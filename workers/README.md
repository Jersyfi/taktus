# Workers

Separate deployables behind the worker contract (`contracts/worker/v1`). None of them imports
anything from `src/taktus`; each is reached over HTTP and Server-Sent Events, as a foreign worker
would be. How any of them is checked: `contracts/worker/v1/CONFORMANCE.md`.

Each worker has its own image (`<worker>/Dockerfile`), built from the repository root. None of
them is part of the control plane image: a worker executes foreign code, and the control plane
carries none of it (DEC-0011). The control plane reaches a worker through the execution port —
by endpoint, as a process it starts, or as a container it starts from that image
(`docs/architecture/contracts.md` §2.4).

| Worker | What it is | Status |
|---|---|---|
| [`script/`](script/README.md) | a shell wrapper with no AI at all — proof case 1 of the contract, and the worker the conformance suite is proven against | passes the suite in both profiles; the removal test is pending, so not *verified* |
| [`claudecode/`](claudecode/README.md) | the first coding worker: a coding agent behind the contract, with boundaries per tool call, consumption per step, and two authentication modes | passes the suite, faults included, in both modes against its fake agent; the removal test is pending, so not *verified* |
| `mlbench/` | training, evaluation, embeddings, classical ML — proof case 2 | `0.4.0` |
| `codex/` | the second coding worker | `0.4.0` |
