# ADR-0291 — Connected knowledge is compared on the value ledger, and a warehouse figure is exported

**Status:** accepted · extends ADR-0244 (the value ledger), ADR-0241 (views and the export),
ADR-0262 (the warehouse), ADR-0265 (knowledge) · UC-5.5 §2 · UC-5.6 §2 · DEC-0228

## Context

UC-5.5 asks that the effect of connected knowledge on the quality of work be measured. The same
work, with and without a source connected, is compared on the figures of the value ledger
(UC-9.1). ADR-0265 left this open: the value ledger was not built then. It is now (ADR-0244),
but it counts per process and day and cannot tell one run from another.

UC-5.6 asks that every warehouse figure shown in a view or a report be in the export (UC-5.7).
A warehouse figure is a signal's value (ADR-0262 §5): a corridor reads it from a step that
queried the warehouse. The signals are shown at `GET /signals` and in the daily report of
signals. The export, `GET /figures`, held only the figures of the value ledger and the
overview's counts. ADR-0262 said so in its bounds.

## Decision

### 1. A run is with or without knowledge by what served its knowledge read

A **knowledge read** of a process version is a step whose work is a connector call of the
capability that one of the version's `citation` steps names (ADR-0265 §3). A run of such a
version is **with knowledge** when one of its knowledge reads finished with a result produced by
a connector: the ledger's `step.finished` names an adapter, and the method is not `human`. Every
other run of that version is **without knowledge**: the source was not connected, or not for
the asker, and the read fell back to a person or failed. A rehearsal is no work and is left out.

The rule reads the ledger and the process version only. A version without a `citation` step has
no knowledge read, and its process is not compared.

### 2. The two sides are compared on the cockpit's figures, at read time

The comparison is computed on every read and stored nowhere. Per process, for the runs that
ended in the period, each side gets the cockpit's figures by the value ledger's own definitions:
the mean cycle time, the quality, the cost per case, the automation and the escalation rate.
The cost per case is accounting's spend of the side's runs, at each run's own price table, over
its finished runs. The difference of each figure is the side with knowledge less the side
without.

Each figure names its method and its basis: the side, its runs, the knowledge reads, the period.
A side without an ended run withholds its figures, and the difference withholds too, saying
which side has none. No figure is ever zero for want of runs. The figures are read at
`GET /value/knowledge`. A reader sees a process only where they may see it, and a figure only
where their roles are entitled to the cockpit figure it compares.

### 3. A warehouse figure is a figure of the export

A signal is a **warehouse figure** where the step its corridor reads queries through a querying
capability (`ports/connector.py`, `QUERYING`). It is handed to the export as the figure
`signal.warehouse` of its process: the value the corridor judged now, or withheld with the
reason the signal is not measured. Its basis names the signal, the corridor in force, the level,
the thresholds, the run and the step of the newest reading, and the query by reference: the
operation, whether the query is fixed in the version, the seq and digest of the ledger's
`query.sent` entry, and the path where a person entitled to the run reads its text. The export
and the views select it by the same entitlement as every other figure (ADR-0241 §2).

## Alternatives

- **A second projection of the value ledger per run.** It would keep one record per run for
  ever. The comparison is read seldom; folding it at read time costs one read of the ledger's
  run and step entries, as accounting's spend does.
- **A run marked with knowledge by its citation alone.** A cited answer needs a search that found
  something. A run whose source was connected and found nothing would count as without.
- **Every signal in the export.** UC-5.6 asks for the warehouse's. A signal over another step
  is the subject of UC-5.7, which this decision does not settle.

## Consequences

- `components/value/domain/service/knowledge.py`: the sides and their figures.
- `composition/knowledge_value.py`: the comparison, read for the HTTP surface.
- `components/reporting/domain/service/warehouse.py`: a warehouse figure from a judged signal.
- `composition/figures.py`: `signal.warehouse` among the known figures, and the warehouse
  figures read beside the gathered ones.
- `adapters/driving/rest/figures.py`: `GET /value/knowledge`; `GET /figures`, `GET /figures.csv`
  and `GET /views` carry the warehouse figures.
- Tests: `tests/components/value/test_knowledge_comparison.py`,
  `tests/composition/test_knowledge_value.py`, `tests/components/reporting/test_warehouse_figures.py`,
  `tests/composition/test_warehouse_signals.py`, `tests/adapters/rest/test_figures.py`.

## Where this promise ends

- **The comparison is an observation, not an experiment.** The two sides are the runs that
  happened. Their cases may differ in kind and difficulty. A difference says what the records
  show, not that the source caused it.
- **The sides are the same process, not the same version.** A version's knowledge reads are
  taken from that version. Runs of versions without a `citation` step are not compared.
- **A correction counts where it was recorded by the end of the period.** A result corrected
  later changes the comparison of a period already read.
- **The cost is what accounting priced.** A side whose runs no table priced withholds its cost.
- **A warehouse figure is the newest judgement.** The export carries the value the corridor
  judges now, not a history of readings. A signal whose corridor is retired leaves the export.
- **Only the querying capabilities of the port.** A figure read through another capability is
  not a warehouse figure here, as ADR-0262 bounds the list.
