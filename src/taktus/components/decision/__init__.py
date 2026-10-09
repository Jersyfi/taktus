"""Owns decision requests, the decision register, rules derived from it.

What exists today (ADR-0042):

- a decision request as the component keeps it — the one shape of `DecisionRequest.json`, the
  role that decides, the anchor that raised it — raised, answered by a holder of the role, its
  reading sent back and confirmed (`application/service`);
- how an answer is read: a rule that finds exactly one option, never a guess
  (`domain/service/interpretation.py`);
- the register: one entry per applied request, linked to its run, step and request;
- the decider's list with what is overdue, and response times that only the decider reads under
  their name (`application/query`, `domain/service/response_times.py`).

Which acts are anchored is governance's; who holds a role is identity's, asked through
`ports/deciders.py`. Rules derived from the register arrive with `0.6.0`.
"""
