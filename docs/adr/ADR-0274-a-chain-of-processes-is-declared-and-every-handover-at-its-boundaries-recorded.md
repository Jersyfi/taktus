# ADR-0274 — A chain of processes is declared, and every handover at its boundaries recorded

**Status:** accepted · extends ADR-0005, ADR-0021 · UC-15.4 · DEC-0228

## Context

UC-15.4 requires that Taktus links the processes of several domains into chains — order to cash,
procure to pay — and hands over the context and the documents completely at every boundary
between domains. A chain is a declared object of its own: which processes it links, in which
order, and what passes at each boundary. At every boundary the handover is recorded: which data
and documents went across, and the clause of the chain that required them. A handover that would
leave out an item the chain declares does not happen: the chain halts there and escalates.

Each process could run on its own, and none knew of another; nothing declared what passes between
them.

## Decision

### 1. The chain is a declaration of its own

A chain document names its `id`, its `links` — process versions in order — and, for every
boundary between two links, `handover`: each item the receiving process is given, as the input it
fills, the step of the sending process whose result it is, the part of that result
(`select`), and the `clause` of the chain that requires it, in words. The process component holds
its shape and its rules (`domain/model/chain.py`, `domain/service/chains.py`): links named
once, every input the receiving version requires given by exactly one item, every item from a
step of the sending version.

### 2. A chain runs link by link

`ChainRuns` (`composition/chains.py`) starts the first link's run with the chain's inputs. When a
link's run finished, the handover is built from its recorded results by the rule: every declared
item, read from the object store by the step run's checkpoint. Where an item is missing, nothing
is handed over: the ledger records `chain.halted` naming the boundary and the items, and the
chain escalates to a person (UC-4.5). Otherwise the ledger records `chain.handover` with the
document of the handover by digest — each item with its value's digest, the step it came from
and its clause — and the next link starts with exactly these items as its inputs. A link that
did not finish stops the chain at that link: one that waits at an anchor waits there, and the
links before it keep their results.

## Alternatives

- **One process holding every domain's steps.** UC-15.4 keeps each link a process with its own
  version, owner and autonomy level.
- **The receiving process reads the sending process's results itself.** Nothing would say what
  crossed the boundary, nor why.

## Consequences

- `chain.handover` and `chain.halted` are new ledger kinds.

## Where this promise ends

- **The chain is not stored or triggered by the instance.** It is a document a caller hands to
  `ChainRuns`; a chain's own trigger, its storage and its surface are not built.
- **No resumption across the boundary.** A link that halted is resumed as its run; the chain does
  not go on by itself after the person decided.
- **No objectives or value balance of a chain**, and no test of a decoupled link beside a coupled
  one: each link runs in its own version's control mode (ADR-0272), and nothing more is shown.
