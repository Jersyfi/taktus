# ADR-0226 — The value ledger counts the correction rate, and a model's explanation names the statement

**Status:** accepted · builds on ADR-0082, ADR-0152 §6 and ADR-0105 · closes what ADR-0152's
*Where this promise ends* left open about the measured rate, a model's explanation and the
blueprints' reports · serves UC-6.9 · issue #224

## Context

The exactness statement of a process version says which checks apply, what they cover, what
they do not cover, and the residual risk (ADR-0082). Its last line was to carry the **measured
rate**: how many results a person corrected after the checks passed, per hundred. Nothing counted
it, so the statement said "not yet measured". UC-6.9 §2 also allows a language model to explain
the statement to a reader, if the explanation names the statement it explains; nothing did. And
no report of a shipped blueprint named the statement, though several carry numbers.

## Decision

### 1. The value component counts the rate

The `value` component owns the value ledger's figures (ADR-0029). Its first figure is the
correction rate, folded from the ledger into the projection `value.corrections.v1` (ADR-0105):

- a result **counts** when its step finished as `succeeded` outside a rehearsal;
- it is **corrected** when a person recorded `step.corrected` for it; a result corrected twice is
  one corrected result, and a correction of a result that never counted is not counted.

`CorrectionRates.of(tenant, version, checked)` answers for the steps that declare a check: the
checks run before a value counts (ADR-0152), so a counted result of a checked step passed them.
The projection keeps a count per version and step and the runs corrected. It keeps no actor:
the rate is a figure about a process, never about a person (principle 14).

### 2. The statement carries the figure it is given

`exactness.statement` takes the figure as `measured` — corrected and counted — from whoever reads
the statement, and writes it as the residual risk's last line: "a person corrected N of M counted
results of its checked steps after the checks passed, R per hundred". Where no result counted
yet, the line says so. Without a figure it keeps the old line. The process component never reads
the ledger itself: the composition reads the figure from the value component and hands it in
(`composition/levels.py`, `measured_of`), for the process level, every run, the overview and a
report's `{"$run": "exactness"}`. No view computes it.

### 3. A model's explanation names the statement it explains

An `llm` step whose prompt reads `{"$run": "exactness"}` receives the statement unchanged. What
leaves the step carries `explains` — the version and the SHA-256 digest of the statement as
rendered — and the run appends to the model's text a closing line naming the version and the
digest, and saying that the statement itself is what holds. The line is the run's, written after
the step's pattern judged the model's text, so a model cannot omit or alter it.

### 4. The blueprints' reports carry the statement

The reports of S-01 (removal test), S-05 (guides), S-06 (maturation) and B-7.05 (review), each
carrying numbers, name `{"$run": "exactness"}` and place it after their figures. Each is a new
version: S-01 3, S-05 5, S-06 3, B-7.05 2.

## Alternatives

- **Count the rate in the governance component's corrections (UC-7.5).** That count serves the
  fall of a level per action class and reads corrections by action. The statement asks a figure
  per version over checked steps. Two definitions in one place would drift; the value ledger owns
  value figures (ADR-0029).
- **Store the rate in the statement.** The statement is computed whenever it is read and never
  stored (ADR-0082). A stored rate would be stale the moment a person corrects a result.
- **Ask the model to cite the statement.** A model may forget or misquote it. A line the run
  writes after the model answered cannot be left out.

## Consequences

- `components/value/domain/service/corrections.py` and `application/query/correction_rates.py`;
  projection `value.corrections.v1` in the table `ledger_projection`. No migration.
- `exactness.statement(..., measured)`, `measured_rate` and `NONE_COUNTED` in the process component.
- `RepositoryLevelRecords` and `VersionStatements` take `rates`; the daemon and `composition/local.py`
  wire them. The replay leaves it out: a rehearsal reads no value ledger.
- An `llm` step's result may carry `explains`; `explaining` in `execute_run.py`.
- A report step that names the statement fails where no statement can be read, as before; engines
  built for tests now wire one.

## Where this promise ends

- The rate counts corrections a person recorded. A wrong result nobody corrected is not in it, so
  the rate is a floor of what slipped through, never an estimate of it.
- It counts from the first entry of the ledger; it is not windowed. A rate over a period is a
  later figure.
- A step without a check is left out of the rate: the statement names it as unchecked instead.
- The closing line proves which statement the model read. It does not prove the explanation is
  right: the explanation is a text of class `free`.
- Reports of other blueprints carry the statement only once their authors name it.
