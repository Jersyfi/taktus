# Workers

Separate deployables behind the worker contract (`contracts/worker/v1`). None of them imports
anything from `src/taktus`; each is reached over HTTP and Server-Sent Events, as a foreign worker
would be. How any of them is checked: `contracts/worker/v1/CONFORMANCE.md`.

| Worker | What it is | Status |
|---|---|---|
| [`script/`](script/README.md) | a shell wrapper with no AI at all — proof case 1 of the contract, and the worker the conformance suite is proven against | passes the suite in both profiles; the removal test is pending, so not *verified* |
| `mlbench/` | training, evaluation, embeddings, classical ML — proof case 2 | `0.4.0` |
| `claudecode/`, `codex/` | the coding workers | `0.1.0` and `0.4.0` |
