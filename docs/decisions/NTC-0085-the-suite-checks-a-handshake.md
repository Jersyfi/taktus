# NTC-0085 — The suite checks a handshake

**Mode entry:** M2.2
**Kind:** test-strategy
**Decided:** 2026-10-09
**Raised in:** the pull request for issue #145

## 1. What was decided

The connector conformance suite checks a handshake where the scenario names one. A handshake is
a signed delivery that is no event, which a connector answers once it verified the signature
(ADR-0024, amendment of 2026-10-09).

- **New, the scenario:** the optional part `intake.handshake` names one recorded handshake and
  the answer the connector must give it — a media type and a body.
- **New, cases of C-08:** the suite delivers the handshake signed and expects a refusal as
  `unsupported_event` with exactly that answer. It then delivers it unsigned, wrongly signed and,
  under `hmac-sha256-timestamped`, an hour stale, and expects each refused with its reason and no
  answer. Answering before verifying is answering anyone, so the four cases belong to C-08.
- **The chat connector has a fault for it.** `C-08-handshake` answers the service's URL
  verification before its signature is verified; the meta-test shows the suite failing on C-08
  alone.
- **The chat connector's scenario changed its unsupported payload.** It was the URL
  verification, which is now the handshake. It is now an edited message, which the connector
  refuses as `unsupported_event` without an answer.
- **Nothing changes for a scenario without a handshake.** The repository connector's run of the
  suite delivers the same payloads as before, and its meta-test is unchanged.

## 2. The evidence

- `make gate-conformance`: the chat connector passes C-01 to C-09 with C-10 pending, now with
  the four handshake cases, and each of its thirteen faults fails exactly its check
  (`tests/conformance/test_connector_v1_chat.py`). The repository connector passes as before.
- `make gate-contracts`: the scenario of a chat connector in the contract's examples names a
  handshake; a handshake without its answer is refused as a scenario.

## 3. What was considered

- **Check only that some answer comes back.** Not taken: a connector that answers with a
  constant would pass, and the service would still reject the address. The scenario states the
  answer, and the suite compares it exactly.
- **A check of its own, C-11.** Not taken: the numbered checks are the contract's, and an
  answer to an unverified delivery is the failure C-08 already names — a delivery processed
  without its signature verified.
- **Keep the URL verification as the unsupported payload.** Not taken: the case would then pass
  whether or not the connector answers it, and say nothing.

## 4. Which entry permits it

M2.2: "A change of test strategy and what the tests now cover." The suite now covers the
handshake and its refusal when unverified. The contract change it rests on adds an optional
scenario part, breaks nothing that conformed, and is recorded where an ADR change of this tenant
is recorded, in the ADR itself (M1.9).
