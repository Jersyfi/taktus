"""Owns the reader's side: views and who may see them, reports and when they are delivered to
whom, and the explanation of an action given on request (ADR-0029). It owns no figure: every
number it shows is read from the component that produces it.

What exists today:

- the product finding (UC-6.12, ADR-0046): what an instance met that the product lacks — a
  capability no configured adapter offers, an operation a connector does not support. A rule
  reads it from the run's blocked-time accounts (`domain/service/findings.py`). The findings
  are grouped by the lack and written in the shape of the issue form `Task`
  (`domain/service/texts.py`). They are shown to the operator, and sent to the Taktus
  repository where the operator enabled it (`application/service/product_findings.py`). The
  blocks and their durations are the run's; the channel a finding is sent through is a port
  (`ports/findings.py`) that the composition root binds to a connector.

A finding names no person (principle 14): its values have no field that can hold one.
"""
