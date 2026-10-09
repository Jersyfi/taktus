"""Owns the reader's side: views and who may see them, reports and their delivery (ADR-0029).
It owns no figure: every number it shows is read from the component that produces it.

What exists today (ADR-0045, UC-6.11):

- the owner-facing channel of a tenant: who the owner is, whom they named, where reports go,
  and the phrasebook in the owner's language (`domain/model/channel.py`);
- a report to the owner — a decision request addressed to them, a need, a date or a failure
  Taktus noticed about itself — with what is needed, the steps, what stands still and the date,
  its deliveries and its history (`domain/model/report.py`);
- its three renderings, composed from the report alone: the repository text, the message in
  the owner's channel, and the view (`domain/service/rendering.py`, `application/query`);
- the owner's answer in the channel, read by a rule, reflected back, filed only once the same
  person confirmed it, and only from the owner or someone the owner named
  (`application/service/answer_in_channel.py`).

Which connector carries a message, how a decision answer is kept and which values are secret are
asked through `ports/`, and answered by the composition root, because components never import
each other.
"""
