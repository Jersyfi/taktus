# NTC-0084 — A verified handshake is answered by the intake

**Mode entry:** M2.4
**Kind:** behaviour-change
**Decided:** 2026-10-09
**Raised in:** the pull request for issue #145

## 1. What was decided

The webhook intake of the HTTP surface, `POST <prefix>/intake/{channel}`, answers a handshake.
A handshake is a signed delivery that is no event: a source system checks an address before it
sends events there, and accepts the address only when the answer carries back a value it sent.

- **Old:** the connector serving the channel refused every delivery that was not an event, and
  the surface answered every refusal of that kind with `202` and a body of its own. The chat
  service's check of the address never succeeded, so the service could not be pointed at an
  instance, and no message written in the chat could reach Taktus.
- **New:** once the connector verified the signature, it may refuse the delivery as
  `unsupported_event` and add an `answer`: a media type and a body. The surface then answers
  with status `200`, that media type and exactly that body, and keeps nothing. The chat
  connector answers its service's URL verification with the challenge, as plain text.
- **Unchanged:** an unsigned, wrongly signed or stale handshake is refused as `unsigned` or
  `bad_signature` and answered `401`, like every delivery; the contract forbids an answer on
  those reasons. Every other refusal is answered as before. The repository connector answers no
  handshake. Nothing under `src/taktus/components/` changed: the `command` component passes a
  refusal through as the connector stated it, and the answer travels inside it.

The contract change it rests on is ADR-0024's amendment of 2026-10-09: the optional field
`answer` on `Refusal` (`IntakeAnswer`), allowed with `unsupported_event` alone.

## 2. The evidence

- `tests/adapters/rest/test_intake_over_mcp.py`: a recorded, signed URL verification posted to
  `/taktus/instance-a/intake/channel.chat` reaches the chat connector over MCP and comes back
  `200`, `text/plain`, with exactly the challenge; the same check unsigned, wrongly signed and
  signed an hour early comes back `401` without the challenge; no intake event is kept. The
  repository connector's ping is still `202`, refused without an answer.
- `tests/adapters/rest/test_surface.py`: a scripted refusal with an answer is returned as it is
  under the root and under a prefix, in two media types, and leaves nothing behind; the module
  of the route names no product and no handshake.
- `tests/adapters/connectors/test_chat_intake.py`: the connector answers the verified check with
  the challenge, answers no unverified one, and refuses a check without a usable challenge as
  `malformed`.
- `make gate-contracts`: an answer on `bad_signature` fails as it must, and so does a media type
  that is none.

## 3. What was considered

- **A third branch of the intake result, beside `accepted` and `refused`.** Not taken: a
  handshake keeps nothing and executes nothing, which is what a refusal already means wherever
  one is handled. A third branch would have made the `command` component learn a case that
  changes nothing it does, and issue #145 requires that it changes nothing.
- **The surface recognising the handshake itself.** Not taken: the surface would have had to
  name the service's message type, and only the connector knows its service. It would also have
  answered before any signature was verified.
- **A status code in the answer.** Not taken: the one known handshake needs `200`. The bound is
  stated in ADR-0024's section *Where this promise ends*.

## 4. Which entry permits it

M2.4: "A change of what the software does, made inside an agreed scope, that breaks no
contract, moves no limit or autonomy level and says nothing public." The scope is issue #145,
ready in milestone `0.2.0`. The contract change adds an optional field and breaks nothing that
conformed, and `v1` is not yet released (ADR-0019), so M3.5 is not touched; the ADR's change is
the session's under M1.9.
