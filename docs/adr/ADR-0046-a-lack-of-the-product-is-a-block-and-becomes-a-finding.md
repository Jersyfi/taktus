# ADR-0046 — A lack of the product is a block, and becomes a finding

**Status:** accepted · amends ADR-0043 §4: a step that failed for want of an adapter is blocked
until it can start

## Context
UC-6.12 requires a *product finding*. An instance of Taktus that meets something the product lacks
raises an issue in the Taktus repository. The issue carries the run, the cause of the block and the
time waited, taken from the blocked-time accounts (ADR-0015, ADR-0043). An instance raises one on
its own only for a block whose recorded cause is a lack of the product: a capability no configured
adapter offers, or an operation a connector does not support. A rule over the recorded block
decides. The same lack met again adds to the open finding instead of opening a second one. A
finding carries identifiers, causes, durations and counts only, and names no person. An instance
outside the Taktus project sends findings only where its operator enabled it.

Until this decision no block had such a cause. A step whose adapter is not configured fails, and
its run escalates at the step boundary; a resume after the configuration changed retries it
(NTC-0002). ADR-0043 §4 and NTC-0090 counted that failure as no block. So the accounts held
nothing a finding could be taken from, and the requirement could not be met.

The reporting component owns views and reports and no figure of its own (ADR-0029). Its package
did not exist yet; it is created with the first `reporting` use case that is built, which this is.

## Decision

### 1. A lack is a block, booked to `wait.dependency`
A step that fails for want of an adapter carries a block from that moment. Its cause token says
which lack it was:

| Cause token | What was lacking |
|---|---|
| `no_worker` | no configured worker offers the capabilities the step requires |
| `no_connector` | no configured connector serves the capability the step calls |
| `operation_unsupported` | the connector that serves the capability does not offer the operation |

The block also carries what was lacking, as an identifier: the capabilities, comma-separated, or
the operation (`OpenBlock.lacking`). It is booked to `wait.dependency`: the step depends on an
adapter the instance does not have. The step still fails and the run still escalates, as NTC-0002
decided. A retry that meets the same lack keeps the one block, so its waiting is one stretch. The
block ends, with its record and `step.waited`, when the step can start: its worker resolves, or its
connector and operation do. The record carries `lacking` as well.

### 2. Open blocks can be read
`BlockedTime` gains a fourth read, `waiting`. It reads every block that has not ended from the step
runs that carry it. A lack that is never repaired never ends, and a finding must not wait for that.
An open block stays in no sum.

### 3. The rule, and one finding per lack
The `reporting` component reads every block, ended and open, through its own port `Blocks`. The
composition root binds the port to `BlockedTime`, so neither component imports the other. A block
is a finding when its cause is one of the three tokens and it names what was lacking as an
identifier. Nothing else decides. A *lack* is the cause and what was lacking. Every block for the
same lack is an *occurrence* of it: the run, the step, when it began, and how long it waited once
it ended.

### 4. A finding in the shape of a task, its state in its own text
A finding opens an issue labelled `task`, with the sections of the issue form `Task`: what must be
achieved, how it is verified, where the boundary lies, the component, the source and what blocks
it (DEC-0051). Below the form's footer it lists its occurrence. Each later report is a comment on
the same issue: a new occurrence, or the end of one reported while it lasted, with the waiting of
every occurrence that ended summed.

Every text carries a *mark*: an HTML comment, not shown, stating the lack, the occurrence, its
state and its waiting. What the repository holds is read from the marks. The instance keeps no
memory of what it sent, so a restart sends nothing twice. Every write carries an idempotency key
derived from the lack, the occurrence and its state, so a repeated call is recognised by the
connector (ADR-0024). A lack whose finding is open is added to it. A lack whose finding was closed,
and met again, opens a new one. The end of an occurrence whose finding was closed meanwhile is not
sent.

Every text sent is recorded in the tenant's ledger as `finding.sent`, with the run and the step it
is about, the channel's adapter, `opened` or `added`, and the text's digest.

### 5. Sent where the operator enabled it, shown everywhere
`TAKTUS_FINDINGS_CONNECTOR` names the MCP address of a connector that serves `repository.issues`
and `repository.comments` on the Taktus repository. Where it is set, the scheduler sends the
findings of every tenant once per ten minutes while it leads, as Taktus itself (ADR-0033). Where it
is not set — the default — nothing is sent. The findings are still recorded, in the blocked-time
accounts they are read from, and `taktusctl findings` shows each one in the words it would be sent
in, ready to send by hand. The Taktus project's own instance is enabled the same way, by its
operator.

### 6. No content, no person
Every value of a finding is closed and holds only identifiers, times, durations and counts, each
to a pattern. What was lacking that is not an identifier makes no finding. There is no field for a
person: neither who met the lack nor who resumed the run.

## Alternatives
- **A finding raised when the block ends.** Rejected: a lack that is never repaired never ends,
  and the product would never hear of it.
- **A lack booked to `wait.human`, because a person must configure the adapter.** Rejected: it
  would mix the time a lack lasts into the waits on people, which principle 14 keeps apart and the
  analysis reads as a person's response time.
- **A record of sent findings on the instance.** Rejected: a second state beside the repository's
  own. The marks in the issue are the state, and they survive a restart and a second instance.
- **A process blueprint for the finding.** Rejected for now: a process would need a rule that reads
  the accounts, which no rule kind does yet. The service is the smaller change.
- **A new operation to edit an issue's body with the running total.** Rejected: the connector does
  not offer it, and a comment per report keeps every figure as it was sent.

## Consequences
- `OpenBlock.lacking`, `Block.lacking` and the record's `lacking`. `step_run.block` is a JSON
  column, so no migration is needed.
- `BlockedTime.waiting`, and `BlockedTime` takes the run repository for it.
- The package `src/taktus/components/reporting/` with its independence contract; the composition's
  `findings.py`; the setting `TAKTUS_FINDINGS_CONNECTOR`; the command `taktusctl findings`.
- A run that escalated for want of an adapter now writes `step.waited` when the step starts on a
  retry, before `step.admitted`.

## Where this promise ends
A finding is raised for the three lacks a step meets at its boundary. A model that is not
configured for a purpose is not one: it is a configuration of the instance far more often than a
lack of the product, and its step fails as before with no block. An awkward flow, a connector that
does too little inside an operation it offers, or anything else a person notices, a person raises
by hand. A lack is a lack of the instance's configuration as much as of the product: an instance
that did not configure an adapter the product has raises a finding all the same, and the product
answers it in its turn. What a finding publishes are identifiers a project chose — run and step
identifiers, capability and operation names. A project whose identifiers say more than it wants
public must not enable sending. The marks can be written by anyone who comments on the issue, so a
false mark changes the counts a later report states. The scheduler reads at most twenty pages of
issues and twenty of each finding's comments; a repository with more sends nothing and logs why.
A finding names no person, but the issue's comments are open to people, and what they write is
theirs.
