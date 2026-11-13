# ADR-0301 — A chain is stored, started and shown by the instance, and goes on by itself at its boundary

**Status:** accepted · extends ADR-0274, ADR-0288 · UC-15.4 · DEC-0236

## Context

ADR-0274 made a chain a declaration and ran it link by link through `ChainRuns`. It drew three
boundaries. The chain was a document a caller handed in: nothing stored it, nothing started it,
and no surface showed it. A link that waited for a person stopped the chain, and the chain did
not go on after the person decided. Nothing showed a decoupled link beside a coupled one.

UC-15.4 requires all three. An anchor in one link stops the whole chain at that link's step
boundary, the links before keep their results, and the chain resumes at that boundary once the
person has decided. Taktus shows the chain as a whole. Every link keeps its own control mode.

## Decision

### 1. The tenant declares a chain, and the instance stores it

`ChainRuns.declare` holds the chain to the versions it links, by the rule of ADR-0274. A chain
that holds is stored as `DeclaredChain` under its identifier (`process/domain/model/chain.py`),
and the ledger records `chain.declared` with the chain's document by digest. A new declaration
replaces the one before. The table is `declared_chain` (migration `0111`).

### 2. A run of a chain is a record of its own

Every run of a chain is a `ChainRun`, stored in `chain_run`. It holds the chain it started with,
so a later declaration does not change it. It holds the link it stands at, the run of every link
that started, the digest of every handover, and its state:

- `running` while a link runs;
- `waiting` when a link did not finish — it waits for a person, at an anchor, or escalated;
- `halted` when a handover lacked a declared item (ADR-0302);
- `finished` when the last link finished;
- `stopped` when a person stopped it.

Its identifier is `chr_<chain>_<n>`, counted per chain. Each link's plan keeps the identifier
`pln_<chain>_<n>`, which the value balance per chain reads (ADR-0288).

### 3. The chain goes on by itself

`ChainRuns.advance` looks at every waiting chain run of a tenant. Where the run of the link it
waits at has finished, it builds the handover from that run's results and starts the next link.
The links before are not run again. The scheduler calls it once a minute for every tenant
(`chains_tick`). The person's decision is the one the link's own run asked for: an answer to a
human step, a decision at an anchor, or the resume of an escalated run.

### 4. A person starts and reads a chain through the HTTP surface

- `PUT /chains/{chain}` declares a chain; only the role `owner` may.
- `POST /chains/{chain}/runs` starts it with its inputs; only the role `owner` may.
- `GET /chains` lists the declared chains with their latest run.
- `GET /chains/{chain}` shows one: its links, every handover's items with their clauses, its
  objectives and its runs.
- `POST /chain-runs/{id}/decision` carries a person's decision on a halted chain (ADR-0302).

A reader sees a chain only where they may see every process it links (ADR-0055 §5). The web app
shows the same under `/chains`.

### 5. Every link keeps its control mode

A link runs in the control mode of its own version (ADR-0272). A decoupled link asks its
external tool at each of its own step boundaries, and a coupled link beside it never does. A
link the tool withdraws is halted, and the chain waits at that link.

## Alternatives

- **A chain as a process version of its own.** UC-15.4 keeps each link a process with its own
  version, owner and autonomy level; a chain links them and is not one of them.
- **The chain going on from the run engine when a run finishes.** The run component would learn
  of chains. A look once a minute costs at most a minute at each boundary, and keeps the engine
  unaware.
- **Revisions of a declaration, as for value streams.** A run keeps the chain it started with,
  which is the history a reader needs; a revision kept beside it would be a second record.

## Consequences

- Migration `0111`: tables `declared_chain` and `chain_run`.
- `chain.declared` and `chain.stopped` are new ledger kinds.
- The scheduler gains `chains_tick`; the HTTP surface the routes of §4; the web app `/chains`.

## Where this promise ends

- **A chain has no trigger of its own.** It is started by a person, or by a caller of the HTTP
  surface. A schedule or an event does not start a chain.
- **Going on takes up to a minute.** A chain goes on at the scheduler's next look after its
  link finished, not at the moment it finished.
- **A link that waits for a person is decided in its own run.** The chain neither asks nor
  reminds. A link whose run is never decided leaves the chain waiting.
- **A replaced declaration does not move a running chain.** It runs to its end with the chain
  it started with.
- **The run counter is not a lock.** Two runs of one chain started in the same instant may be
  given the same identifier, and the second replaces the first's record.
