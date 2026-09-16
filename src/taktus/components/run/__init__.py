"""Owns run, step run, checkpoint, artifact, and — until governance exists — admission control.

A run executes the steps of a commissioned plan one at a time, in the plan's order. Around
every step the same four things happen (ADR-0005): its demand is estimated and checked against
what remains of the run's budget — a step that does not fit is rejected before it starts, never
aborted after; it runs; its checkpoint, its artifacts and its raw consumption are persisted; and
a stop that was requested meanwhile takes effect now, at the boundary. Every state change goes
to the ledger through the ledger port.

Consumption is raw here — tokens, compute seconds and their class, quota units, money by
currency. The normalised Takt is derived elsewhere (docs/architecture/accounting.md).
"""
