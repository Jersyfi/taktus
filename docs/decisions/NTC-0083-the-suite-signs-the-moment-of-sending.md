# NTC-0083 — The suite signs the moment of sending

**Mode entry:** M2.2
**Kind:** test-strategy
**Decided:** 2026-10-09
**Raised in:** [#148](https://github.com/Jersyfi/taktus/pull/148), for issue #84

## 1. What was decided

The connector conformance suite signs intake payloads under a second scheme, and checks one more
refusal under it.

- **Old:** the suite signed the raw body of a recorded payload with the intake secret, and put
  the digest in the header the scenario names. A target that signs anything else could not be
  checked: its connector failed C-07 and C-08 whatever it did.
- **New, the scheme:** a connector may declare `hmac-sha256-timestamped` (ADR-0024, amendment of
  2026-10-09). Its scenario then names, under `intake.signature.timestamp`, the header of the
  moment of sending and the version token. The suite writes that header itself, with the moment
  it says the payload arrived, and signs `<version>:<moment>:<body>`.
- **New, a case of C-08:** under that scheme the suite also delivers the supported payload signed
  correctly an hour before it arrived. It expects `bad_signature`: the scheme's point is that a
  captured delivery cannot be sent again later.
- **The chat connector has a fault for it.** `C-08-stale` stops checking the moment, and the
  meta-test shows the suite failing on C-08 alone.
- **Nothing changes for `hmac-sha256`.** The repository connector's run of the suite delivers the
  same payloads with the same signatures as before, and its meta-test is unchanged.

## 2. The evidence

- The chat service signs `v0:<moment>:<body>` and sends the moment in a header of its own. The
  chat connector verifies exactly that (`src/taktus/adapters/driven/connectors/slack/intake.py`).
- `make gate-conformance`: the chat connector passes C-01 to C-09 with C-10 pending, and each of
  its twelve faults fails exactly its check (`tests/conformance/test_connector_v1_chat.py`). The
  repository connector passes as before, with a token and as the app, and its faults fail as
  before.
- `make gate-contracts`: the schema's new value and field validate, a scenario with a moment's
  header and no version token is refused, and the examples of a chat connector use the new
  scheme.

## 3. What was considered

- **Leave the suite alone and let the chat connector accept a signature over the raw body.** Not
  taken: the real service never sends one, so the connector would carry a second, weaker
  verification path that exists only to pass a test.
- **A scenario field naming the whole signed string as a template.** Not taken: two schemes are
  known, and a template would let a scenario describe a scheme the contract does not name. The
  scheme is the contract's; the scenario only names where its parts go.
- **No stale case.** Not taken: a connector that verifies the digest and ignores the moment
  passes every other check, and the bound on replay is the reason the scheme exists.

## 4. Which entry permits it

M2.2: "A change of test strategy and what the tests now cover." The suite now covers a second
signature scheme and its bound on replay. The contract change it rests on adds a value and an
optional field, breaks nothing that conformed, and is recorded where an ADR change of this
tenant is recorded, in the ADR itself (M1.9).
