# ADR-0192 — The processes of software-operations select by a rule, and the blueprint proposes the anchors of its domain

**Status:** accepted · extends ADR-0042 (anchors per tenant), ADR-0095 (the rule `extract`)
and ADR-0137 §6 (a blueprint proposes its stages) · issues #400, #437, #401, #438, #439, #440,
UC-03 §4, §6, §9

## Context

UC-03 names the processes each stage of the second tenant's introduction adds. Most of them
read a list from a system — errors, open issues, series of a metrics store, checks — and must
pick from it: the errors that reach many users, the function with the highest error rate, the
checks that failed. The rules a `rule` step can evaluate had no way to do that. `check` holds
one value, `extract` composes texts from patterns, and a reference selects one part of a value,
never every item of a list. A model could pick, but a figure that steers an incident or the
issue filed must be reproducible (CLAUDE.md §3, §4).

UC-03 §6 lists what stays with a person at every stage: moving money, legal responsibility,
staff, its own limits, cheating to green, promises, mass sending and user data. Stage 2 (#401)
asks that a run halt at a legal anchor wherever money would move. UC-03 §9 asks that a test run
a level-4 process into each row and find it halted. The shipped default anchors
`payment.release` and `legal.*`, but not every act that moves money: a refund or a credit would
pass it.

## Decision

### 1. A rule that filters a reading

The rule kind `filter` keeps the items of a list that its conditions keep:

| Field | Meaning |
|---|---|
| `items` | the list, usually a reference to a reading; every item an object |
| `all`, `any` | conditions over a field of the item, by a dotted path: `equals`, `matches`, `not_matches`, `at_least`, `at_most`. Every one of `all` must hold, and one of `any` where given |
| `excluding`, `within`, `marker` | texts, or objects whose `within` field is the text; an item whose `marker`, composed from its fields as a `template` composes, occurs in one of them is left out |
| `order`, `descending`, `limit` | sorted by a field, numbers as numbers, then cut |

The result is `items`, `count`, and `first` where anything is kept. A number is compared in
decimal arithmetic. A field an item does not carry fails that condition, never the step. The
same lists give the same result: the rule is admissible for `exact`, and a step that uses it
declares the check by recomputation (DEC-0173).

`marker` is how a process files a thing once: the issue B-1.05 files carries
`errors-issue:<id>`, and the next run leaves out every error an open issue carries the mark of.

### 2. The processes of the blueprint

Each process is a bundle under `blueprints/software-operations/processes/`, named
`b-<area>-<number>` (ADR-0191 §4). It names capabilities only. It starts at level 1 where it
only reads and judges, and at level 2 where it acts. It is registered as shipped and run against
the fakes of the systems behind its capabilities in `tests/composition/test_software_operations.py`.
A test holds every operation a bundle calls to one a connector of this repository declares.
The blueprint's README lists, per stage, which processes are built and what each that is not
lacks.

### 3. The blueprint proposes its anchors

A blueprint may carry **`anchors.json`**, beside its `stages.yaml`: the anchor configuration
it proposes, in the shape `taktusctl anchors set` reads. A tenant configures it as it is, or
adapts it. Which role decides is the tenant's; the proposal names `owner`, as the shipped
default does. `blueprints/software-operations/anchors.json` proposes three anchors:

| Anchor | Class | Applies to | UC-03 §6 row |
|---|---|---|---|
| `anc-money` | legal | `payment.*`: every act under the capabilities that move money — a release today, any refund or credit a connector adds there | moving money |
| `anc-legal` | legal | `legal.*` | legal responsibility |
| `anc-correction` | correction | `correction.*` | a correction of a result that left the system (ADR-0022) |

Reading a payment provider's subscriptions is the capability `payments.subscriptions`, a
different first segment. It is not anchored.
`tests/governance/test_software_operations_anchors.py` configures the proposal and runs a
level-4 run into each anchor. Each halts at the step's boundary with a decision request of the
anchor's class, and nothing of the act starts.

## Alternatives

- **A model picks from the list.** The pick would differ between two runs and could not be
  `exact`; a selection over figures is a rule.
- **One run per item, by a trigger's `each`.** Every unresolved error would start a run every
  hour; without a mark, each would file again. One run that filters and files the first unfiled
  item does the same with one confirmation.
- **Widen the shipped default to `payment.*`.** It would change every tenant's default for one
  blueprint's domain. The default is the floor; a blueprint proposes for its own domain.
- **Anchor each process of UC-03 §4.3 by its identifier.** An anchor by process holds every step
  of it, reads included. An anchor by capability holds exactly the act.

## Consequences

- The run's rules gain `filter` (`FilterRule`, `Bound`, `rules.filter_items`).
- `blueprints/software-operations/` gains its processes and `anchors.json`.

## Where this promise ends

- **The filter reads one list at a time.** Matching two lists item by item — a payment against
  an entitlement — is not a filter: B-6.01 is not built until a rule or a statistic for it is.
- **A mark finds only what carries it.** An issue a person filed for the same error without the
  mark is not recognised; the error is filed again, and a person closes one as a duplicate.
- **A process is built only where a connector serves its capability.** What none serves is
  listed in the blueprint's README with the capability it lacks, and is not called.
- **Three rows of UC-03 §6 are anchored here.** Its own limits are held by the product already:
  no process changes a level or a limit (UC-7.1, ADR-0005). Promises and mass sending are
  UC-7.6's; user data outside the case is UC-7.7's. Staff and partnerships have no capability
  yet that an anchor could name. Cheating to green — a change touching a path the tenant
  declares protected — needs the paths a change touches to be known at the step's boundary;
  that is not built, so no anchor here holds it.
- **An anchor holds only what a connector names under its capability.** A connector that moved
  money under another capability would pass it. A connector's review is where its capabilities
  are checked.
- **Not legally reviewed.** The acts named are the project's reading of UC-03 §6 for no
  jurisdiction (DEC-0029). A legal-anchor catalogue reviewed per jurisdiction is UC-15.5.
- **Whether and when the business introduces a process is the business's.** The product
  provides each process and proves it against fakes; running it is the business's, on its own
  instance (DEC-0201).
