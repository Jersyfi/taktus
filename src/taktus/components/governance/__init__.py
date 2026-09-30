"""Owns autonomy levels, policies, anchors, budgets, limits, admission control.

What exists today:

- the checkable half of the correction anchor (ADR-0022): whether a result has left the
  system, decided over provenance records and ledger entries (`domain/service/egress.py`);
- the capacity report (docs/architecture/platform.md, *Observe*): what the platform has left,
  how fast the state grows, and the date a person must act by (`domain/service/capacity.py`,
  `application/service/report_capacity.py`). The refusal of a job that does not fit is the
  run's admission control (`run/domain/service/capacity.py`) until admission moves here.

Anchors as configuration, and the halt they cause, arrive with `0.2.0`.
"""
