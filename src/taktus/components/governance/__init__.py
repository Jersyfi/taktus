"""Owns autonomy levels, policies, anchors, budgets, limits, admission control.

What exists today:

- a tenant's anchors (ADR-0042): the configuration, never emptied, and the shipped default a
  tenant holds while it configured none (`domain/model/anchors.py`); which anchors name a step's
  act (`domain/service/anchors.py`); storing one and reading the anchors in force
  (`application/service/configure_anchors.py`). The run asks before every step through its own
  port; the halt and the decision request it raises are the run's and decision's;
- the checkable half of the correction anchor (ADR-0022): whether a result has left the
  system, decided over provenance records and ledger entries (`domain/service/egress.py`);
- the capacity report (docs/architecture/platform.md, *Observe*): what the platform has left,
  how fast the state grows, and the date a person must act by (`domain/service/capacity.py`,
  `application/service/report_capacity.py`). The refusal of a job that does not fit is the
  run's admission control (`run/domain/service/capacity.py`) until admission moves here.

Autonomy levels 1 to 3 are enforced at the step boundary (ADR-0039). The rule that says which
level holds for a step and what it asks of a person is the run's
(`run/domain/service/autonomy.py`), and the rule that says when a level may rise is the
process's (`process/domain/service/autonomy.py`), where registering a version raises it; both
move here as admission will.
"""
