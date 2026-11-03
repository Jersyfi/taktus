# ADR-0161 — Recurring decisions become rules on a person's acceptance

**Status:** accepted · builds the precedent memory of ADR-0008 and what ADR-0042 left to
`0.6.0` · issue #648, UC-7.10

## Context

Every decision request that takes effect leaves an entry in the decision register (ADR-0042).
ADR-0008 calls the register a precedent memory: once a pattern is consistent, Taktus proposes
turning it into a rule, and autonomy grows through use without control being given away.
ADR-0042 left this to `0.6.0`.

Four questions had to be answered. Which requests may a rule ever answer? What counts as a
consistent pattern? How is a rule proposed and accepted? What does an accepted rule do?

Method maturation (ADR-0084, ADR-0114) already proposes a change as a decision request and
applies it only once a person accepted it. A rule from precedent follows that pattern. It is a
different mechanism: maturation moves a step to another method; a rule answers a request.

## Decision

### 1. Only a tenant's own strategic anchor
A rule may answer only a request raised by an anchor of the tenant's own configuration of the
class `strategic`. The tenant may reduce that class (ADR-0008); a rule a person accepts is such
a reduction, for one kind of request. Every other request keeps its act with a person whatever
the tenant configures, and no rule is ever proposed for it: the classes `legal` and
`correction`, the frame's own anchors, a step's own `ask` (ADR-0088), an approval or a sample
(ADR-0152), a proposal to change a process. The rule is `decision/domain/service/precedent.py`,
`refusal` (NTC-0249).

### 2. A pattern is a count
A *kind* of request is one anchor at one step of one process. The process is read from the
ledger, the run's `run.created`. A pattern holds when the **five** most recent decisions of a
kind, all decided after the last proposal of the kind was decided, chose the same option, by the
same role, without modifications, and none was taken by a rule. The detection is that count. No
language model reads the register.

### 3. The proposal is a decision request
After every decision that took effect, the decision component looks at its kind. Where a
pattern holds, it raises a decision request of class `strategic` to the role that decided the
precedents. The request names every precedent by its register entry, offers to adopt the rule
(option A, recommended, with the count as its reason) or to keep asking (option B), and blocks
nothing. The rule is stored `proposed` (`decision_rule`, migration 0089) and recorded as
`rule.proposed`. A proposed rule answers nothing. One proposal of a kind is open at a time.

The proposal is answered and confirmed as any request is. Option A without modifications adopts
the rule, with the person whose answer took effect as its actor: `rule.adopted`. Any other answer
declines it: `rule.declined`. A declined kind is proposed again only once five decisions after
the decline agree.

### 4. An adopted rule answers at once, and names itself
A request of an adopted rule's kind is still raised. In the same transaction it takes effect
with the rule's option: applied, answered by `rule:<id>`, with a register entry that names the
rule and a `decision.applied` and a `rule.applied` entry without an actor. The run engine asks
the verdict of every request it just raised. When each took effect, the step is decided at once:
it continues from its boundary, ends declined, or halts the run with cause `declined`, as a
person's decision would have it. A rule's decision is no person's confirmation of a step: at
level 2 the step still waits for one. A decision a rule took is nobody's response time
(ADR-0015).

A person retires an adopted rule (`rule.retired`). From then on the kind is asked again.

## Alternatives
- **Rules over every anchor.** A count would then decide a legal act, which ADR-0008 forbids.
- **The rule as a new process version** that drops the anchor or the ask. An anchor is the
  tenant's configuration, not the process's, and a version cannot remove it; an ask cannot be
  removed by the tenant (ADR-0088).
- **Answer by rule without raising the request.** Then the register would lose the decision,
  and nobody could read since when a rule decided.
- **A model to judge whether two requests are alike.** Its verdict would differ between two
  readings of the same register, and principle 8 asks for the same answer every time. The kind
  is a key, compared exactly.

## Consequences
- `DecisionRule`, `PrecedentRules`, `precedent.py`; `RegisterEntry.rule`; `Verdict.by_rule`.
- Migration 0089: `decision_rule`.
- Ledger kinds `rule.proposed`, `rule.adopted`, `rule.declined`, `rule.applied`, `rule.retired`.
- The run engine decides an anchored step at once where every request took effect as it was
  raised.

## Where this promise ends
A rule answers requests of its kind exactly; a request whose situation differs in substance but
comes from the same anchor at the same step is answered the same way, which is what the person
accepted. A rule answers only the option the precedents chose, never one with modifications. The
number five is fixed, not configurable per tenant. Rules are listed, adopted and retired through
the decision component's use cases and the ordinary request surface; no command line or page of
their own exists. A rule outlives a change of the anchor's wording; it ends when the anchor's id
or the step's id changes, or a person retires it. Who may retire a rule is not checked beyond
the identity that asks, until rights per role exist (UC-7.3).
