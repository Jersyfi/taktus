# ADR-0086 — Maturation runs on the instance, from the command line and on a schedule

**Status:** accepted · makes the handlers of ADR-0084 reachable on an instance (issue #229,
roadmap `0.4.0`)

## Context
ADR-0084 built method maturation as three handlers of the run component. `StepMeasures` reads
every step's measures. `CorrectResultHandler` records a person's correction of a step's result.
`ProposeMovesHandler` trains and tries a candidate, and raises a proposal as a decision request
where the evidence holds. ADR-0084 left them unreachable: no command line called them, and no
schedule did. The roadmap's `0.4.0` criterion — a step moved on Taktus's own proposal — cannot be
met on an instance where nothing ever asks for a proposal.

Three questions were open. Where the handlers get the instance's price table and decision port.
How a person reaches them. And what starts maturation without a person.

## Decision

### 1. The handlers are built once, with the instance's price table and its decision port
`composition/maturation.py` builds the three handlers over the instance's stores and run engine.
`taktusctl` (`composition/local.py`) and the daemon (`composition/daemon.py`) call the same
function. Both hand it the table `TAKTUS_PRICE_TABLE` names, which the run engine prices with
too, and the decision port the run engine raises requests through (ADR-0042). A proposal
therefore reaches the owner-facing channel as every other request does (ADR-0045).

Without a price table, every cost a measure reads is named unpriced. A step that would be a
candidate is then not trained: no cost can be compared, so no proposal could rest on one, and
training would spend the budget for nothing. The outcome says so.

### 2. Three commands
`taktusctl maturation` has three commands:

- `measures` prints every step's measures, as lines or as one JSON document. A measure names
  its process version and step, never a person (principle 14). Exit code `1` says that a cost
  could not be priced.
- `correct <run> <step> --value <value> --identity <identity>` records a correction as the
  identity the command names, which must be one the tenant knows (ADR-0040). A step without a
  result is refused, with the reason, and exit code `1`.
- `propose --compute-seconds <n> --identity <identity>` asks for proposals. The budget is what
  each training and each trial may use. `--process-version` and `--step` narrow what is looked
  at; `--as-change` asks for the move as a change and is answered with a proposal all the same
  (ADR-0084 §7). Every step looked at is printed, with the request raised or why none was.

### 3. On a schedule: a self-operation process, S-06
Maturation runs as a process Taktus runs for itself, S-06 of `blueprints/self-operation/`. Its
trigger says `weekly`, Mondays 00:00 UTC, with the budget as the trigger's input. The elected
scheduler starts it once per slot, whichever scheduler leads (ADR-0035). The runs act for the
identity that registered the bundle (ADR-0040), and so do the training and the trial they start.

S-06 reaches the handlers through a new capability of the loopback connector,
`orchestrator.maturation`, with two operations: `measures` and `propose`. Both are `read`. The
training and the trial are runs of their own, each in the ledger with its own effects, as the
removal test's rehearsals are. A proposal is a record of the decision component, which delivers
it and records the delivery itself, as the guides' reports are.

The schedule an instance runs is the trigger of the bundle version it registered. A different
weekday, a different interval or a different budget is a new version of the bundle with that
trigger. Switching S-06 off is `taktusctl deactivate --process s06-maturation`.

## Alternatives
- **A schedule in the instance's environment, run by the scheduler directly.** One variable
  more, and a second way for the scheduler to start work beside the triggers of registered
  processes. A process keeps the run in the ledger, under a budget, with a report a person reads,
  and with a takeover description, as S-01 and S-05 are.
- **Maturation at the end of every run of a step.** It would look at a step after every case.
  Training is expensive and the floor is hundreds of cases; a weekly look is enough to notice a
  step that reached it.
- **The budget as a setting of the instance.** A run's budget is the run's, and the trigger is
  where a scheduled run's inputs come from (ADR-0035).
- **Training without a price table, and refusing afterwards.** That was ADR-0084's behaviour. It
  spends the budget on a training whose verdict is known before it starts.

## Consequences
- `composition/maturation.py`: `maturation_wiring` and `InstanceMaturation`, wired in
  `local.py` and `daemon.py`.
- The loopback connector: the capability `orchestrator.maturation` and its protocol
  `Maturation`.
- `adapters/driving/cli/maturation_command.py`; `Services` gains `measures`, `correct_result`
  and `propose_moves`.
- `ProposeMovesHandler` trains nothing without a price table.
- `blueprints/self-operation/processes/S-06-maturation.yaml`, with its README section and its
  takeover description.
- No migration, no contract change: S-06 is a bundle, and the loopback's declaration is the
  adapter's own.

## Where this promise ends
The schedule starts maturation; it does not make it succeed. A candidate is trained only on a
worker that offers `ml.train` and is at least *verified* on the instance (ADR-0039); until the
ML bench has passed its conformance suite and the removal test there, every weekly run reports
that the training did not finish. The budget of the trigger holds each training and each trial,
not the weekly run as a whole: a tenant with many candidates spends that budget once per
candidate. The measures read every run of the tenant on each call, as ADR-0084 says, and a
weekly run reads them twice. `taktusctl maturation correct` lets any identity the tenant knows
correct any step, until rights per role exist (UC-7.3). Applying an accepted proposal is #218,
and a web page for the measures is not part of this.
