# ADR-0216 — What a process spends is grouped by the case its run names

**Status:** accepted · extends ADR-0148 (spend read per step from the ledger) and ADR-0044 (the
loopback connector) · UC-03 B-2.02, UC-8.5, DEC-0228

## Context

UC-03 B-2.02 asks for the model cost attributed to the process, to the support case or to the
pull request. ADR-0148 reads a process's spend per run and per step, over a window. Nothing
says which case a run was about, and no capability serves the figure to a process: the cost of
a support case could only be added up by hand.

A run already carries its inputs. B-3.02 is started with `message`, the identifier of the
customer's message it answers; a coding run is started with its issue or pull request. What is
missing is which input is the case.

## Decision

### 1. A version names the input that is its case

A bundle may name `case:`, an input it declares under `inputs`. Registration refuses an input
the bundle does not declare. A run's case is the value of that input in the run, as text. A run
whose version names none, or that was given no value for it, belongs to no case. The version
keeps the name in `process_version.case_input` (migration 0100).

### 2. The spend is grouped by case in the accounting component

`SpendHandler.of_cases` takes a process, a window and the case of each run, by run identifier.
It reads the process's runs whose steps finished in the window, rehearsals left out, as
`of_process` does, and prices each run at its own table (ADR-0148). Per case it returns the
runs, the money per currency, the money where one currency holds it all, the Takte and what
could not be priced. The costliest case comes first. A run named in no case is counted apart, as
`without_case`.

### 3. A process reads it through the loopback connector

The loopback connector declares the capability `orchestrator.spend` with one operation,
`orchestrator.spend.cases`, effect `read`. It takes `process` and `days`, from 1 to 366, and
answers the document of §2 for the window that ends now. The instance answers through the
protocol `Spend`, implemented in `composition/case_spend.py`. It reads the versions of the
process for the input each names, and the process's runs for its value.

### 4. The blueprint reads the costliest cases of a week

B-2.02 of `software-operations` reads the cases of B-3.02 over seven days every Monday and keeps
the five costliest, by the rule `filter`. A case whose money is not in one currency is left out
of the order, never read as free. B-3.02 names `message` as its case. A process paused at its
budget is each process's own `limits` (ADR-0005), not this process's act.

## Alternatives

- **A case key on the run itself.** The run carries its inputs already; a second copy could
  disagree with them, and every caller that starts a run would have to set it.
- **The case in the ledger.** The ledger holds identifiers and digests only (ADR-0006); a
  message identifier is the tenant's, kept with the run.
- **A connector of its own.** The figure is the instance's own; the loopback connector is where
  a process asks the instance about itself.

## Consequences

- `process`: `ProcessVersion.case`; registration checks it.
- `accounting`: `CaseSpend`, `CasesSpend`, `SpendOfCases`, `SpendHandler.of_cases`.
- The loopback connector: `orchestrator.spend`, `orchestrator.spend.cases`, the protocol `Spend`.
- `composition/case_spend.py`: `InstanceSpend`, bound in `daemon.py` and `local.py`.
- Migration 0100: `process_version.case_input`.
- `blueprints/software-operations`: B-2.02; B-3.02 names `message`.

## Where this promise ends

- A case is what its version's input names. Two runs about the same customer but started with
  different message identifiers are two cases; a thread of several messages is several cases.
- A run's case is read from the version the run ran. A version that names no case, and a run
  stored before this, belong to no case.
- The read takes every `step.finished` of the tenant once, then each run of the process in the
  window, and every version and run of the tenant to name the cases; its cost grows with the
  tenant's records, not with the window.
- A figure is as complete as what was reported (ADR-0148). An unpriced run is named, never free.
- The case identifiers are the tenant's own and are shown to the process that reads them; no
  figure names a person (principle 14).
