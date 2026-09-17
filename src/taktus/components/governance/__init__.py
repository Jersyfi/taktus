"""Owns autonomy levels, policies, anchors, budgets, limits, admission control.

What exists today is the checkable half of the correction anchor (ADR-0022): whether a result
has left the system, decided over provenance records and ledger entries
(`domain/service/egress.py`). Anchors as configuration, and the halt they cause, arrive with
`0.2.0`.
"""
