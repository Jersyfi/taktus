# NTC-0234 — A tenant without message rules sends no message a model wrote

**Mode entry:** M2.6
**Kind:** unlisted
**Decided:** 2026-10-23
**Raised in:** issue [#435](https://github.com/Jersyfi/taktus/issues/435), in the pull request that closes it
**How it follows:** UC-7.6 §2 says a message a model wrote "carries the tenant's label" and that "a message without it is refused". A tenant that configured no label has none to carry, so refusing the message is the requirement as written. §1 asks for "a sending delay" without naming its length, and UC-03 B-3.03 names a delay as part of every automatic send; a delay of zero would be no delay. Quiet hours are read in the tenant's zone, which Taktus does not know before the tenant names it. Mass sending is "more recipients than the tenant's limit" (§2); a limit is needed before any tenant sets one. The frame's anchors take the role and class of `anc-personal-data` (NTC-0224), for the same reason. Where a stricter and a looser default were both consistent with the sources, the stricter was taken.

## 1. What was decided

ADR-0142 needs values before a tenant sets any.

1. **A tenant that configured no rules has no label.** No message a model drafted is sent
   until `taktusctl messages set --label` gives one. A message no model wrote is not affected.
2. **The sending delay is 600 seconds.** Ten minutes leave a person who is already answering
   in the case the time to do so (§9 of the ADR).
3. **There are no quiet hours.** Without a zone, any span of hours would be a guess about the
   tenant's recipients.
4. **The recipient limit is 10.** A reply to a customer with a few people in copy is not mass
   sending. A list of eleven is held for a person.
5. **The frame's anchors `anc-promise` and `anc-mass-sending` are of class `legal` and are
   decided by the role `owner`**, as `anc-personal-data` is.

All are product defaults, not the project's.

## 2. The evidence

- Before this change no step declared a message frame, and no shipped process delivers what a
  model drafted (`blueprints/`). The defaults therefore change nothing a process did before:
  every test that ran before runs unchanged.
- `tests/components/governance/test_messages.py`
  `test_a_tenant_that_configured_nothing_holds_the_shipped_rules_the_run_holds` holds 1 to 4.
- `tests/components/run/test_outward_messages.py`
  `test_a_message_a_model_drafted_without_a_label_is_refused_before_the_port` shows the first
  default refusing a message.
- `tests/components/run/test_outward_messages.py`
  `test_a_promise_or_a_message_that_cannot_be_classified_waits_for_a_person` shows the anchor
  raised as `legal` at level 4.

## 3. What was considered

- **A shipped label in English.** What the law asks a label to say is the tenant's legal
  responsibility (UC-7.6 §3). A label Taktus chose would be sent under the tenant's name
  without the tenant having said it. Rejected.
- **No delay by default.** A person answering in the case would race the machine. Rejected.
- **A limit of 1.** Every reply with a person in copy would wait for the owner. That is
  ceremony without substance. Rejected.
- **The anchors of class `strategic`.** A strategic anchor may be reduced to nothing
  (ADR-0008). Rejected.

## 4. Which entry permits it

No entry of modes 3 or 4 names a default of a tenant's message rules or the decider of an
anchor the frame raises. M3.10 names limits on spending, and none of these limits spending. No
entry of mode 2 names them either, so M2.6 applies.

## 5. The entry it proposes

The entry NTC-0212 proposed, **M1.24** — *the shipped default of a tenant setting that limits
no spending* — covers all five.
